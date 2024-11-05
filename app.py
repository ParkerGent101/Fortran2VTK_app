import time
from flask import Flask, request, jsonify, render_template, flash, send_from_directory
import paramiko
import subprocess
import platform
import os

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_key')

BASE_UPLOAD_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE_DIR = os.path.join(BASE_UPLOAD_DIR, 'downloaded_files')

if not os.path.exists(LOCAL_FILE_DIR):
    os.makedirs(LOCAL_FILE_DIR)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_from_directory(LOCAL_FILE_DIR, filename, as_attachment=True)
    except Exception as e:
        flash('Failed to retrieve the file: {}'.format(str(e)), 'error')
        return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    username = request.form.get('username')
    password = request.form.get('password')
    files = request.files.getlist('files')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username and password are required.'}), 400

    if not files:
        return jsonify({'status': 'error', 'message': 'No files uploaded.'}), 400

    # Save uploaded files locally
    saved_files = save_files(files)
    if not saved_files:
        return jsonify({'status': 'error', 'message': 'Failed to save uploaded files.'}), 500

    # Establish SSH connection
    ssh = establish_ssh_connection(username, password)
    if ssh is None:
        return jsonify({'status': 'error', 'message': 'SSH connection failed.'}), 500

    try:
        # Upload local files to the remote server
        remote_uploaded_files = upload_files_to_remote(ssh, saved_files)
        
        # Create the Slurm script locally and run dos2unix if on non-Windows
        slurm_script_path = create_slurm_script(remote_uploaded_files)
        if platform.system() != "Windows":
            subprocess.run(['dos2unix', slurm_script_path])

        # Upload the Slurm script to the remote server and submit the job
        job_id = submit_slurm_job(ssh, slurm_script_path)

        # Poll for job completion and download VTK files once complete
        vtk_filenames = poll_for_job_completion(ssh, job_id)
        if vtk_filenames is None:
            return jsonify({'status': 'error', 'message': 'No .vtk files found after job completion.'}), 404

        return jsonify({'status': 'success', 'message': 'Files uploaded and processed successfully!', 'vtk_files': vtk_filenames}), 200
    
    finally:
        ssh.close()  # Ensure SSH connection is closed


def save_files(files):
    saved_files = []
    for file in files:
        if file and file.filename:
            file_path = os.path.join(LOCAL_FILE_DIR, file.filename)
            try:
                file.save(file_path)
                saved_files.append(file_path)
            except Exception as e:
                flash(f'Error saving file {file.filename}: {str(e)}', 'error')
    return saved_files

def establish_ssh_connection(username, password):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('hpc-portal2.hpc.uark.edu', username=username, password=password)
        return ssh
    except Exception as e:
        flash('SSH connection failed: {}'.format(str(e)), 'error')
        return None

def upload_files_to_remote(ssh, local_files):
    remote_uploaded_files = []
    with ssh.open_sftp() as sftp:
        for local_file_path in local_files:
            remote_file_path = os.path.join('/scrfs/storage/prgent/home/', os.path.basename(local_file_path))
            try:
                sftp.put(local_file_path, remote_file_path)
                remote_uploaded_files.append(remote_file_path)
            except Exception as e:
                flash(f'Error uploading {local_file_path}: {str(e)}', 'error')
    return remote_uploaded_files

def create_slurm_script(remote_files):
    # Ensure the script refers to the correct paths for the remote files
    remote_file_paths = " ".join(remote_files)
    
    slurm_script_content = f"""#!/bin/bash
#SBATCH --job-name=vtk_simulation
#SBATCH --output=output.txt
#SBATCH --error=error.txt
#SBATCH --time=72:00:00
#SBATCH --partition=cloud72
#SBATCH --qos=cloud
#SBATCH -N 1          # Number of nodes
#SBATCH -n 1          # Number of tasks
#SBATCH -c 1          # Number of cores per task

# Load necessary modules
module load nvhpc

# Compile the Fortran code with nvfortran
nvfortran -acc -Minfo=accel -fast {remote_file_paths} -o writer.exe

# Make the executable
chmod +x writer.exe

# Run the simulation
srun --pty ./writer.exe
"""
    # Save the script locally
    script_path = os.path.join(LOCAL_FILE_DIR, 'run_simulation.sh')
    with open(script_path, 'w') as script_file:
        script_file.write(slurm_script_content)

    return script_path

def submit_slurm_job(ssh, script_path):
    # Define the remote script path on the HPC
    remote_script_path = f"/scrfs/storage/prgent/home/{os.path.basename(script_path)}"
    
    # Upload the script to the remote server
    with ssh.open_sftp() as sftp:
        sftp.put(script_path, remote_script_path)

    # Set execute permissions for the script on the remote server
    ssh.exec_command(f"chmod +x {remote_script_path}")

    # Execute sbatch command to submit the Slurm job
    stdin, stdout, stderr = ssh.exec_command(f"sbatch {remote_script_path}")
    output = stdout.read().decode().strip()
    error_output = stderr.read().decode().strip()

    # Handle errors
    if error_output:
        flash(f"Slurm submission error: {error_output}", 'error')
        return None

    # Check if we have a valid job ID from the Slurm output
    if "Submitted batch job" in output:
        job_id = output.split()[-1]  # Extract job ID from output
        return job_id
    else:
        flash(f"Failed to retrieve job ID: {output}", 'error')
        return None

def poll_for_job_completion(ssh, job_id):
    # Poll the job queue until the job completes
    while True:
        stdin, stdout, stderr = ssh.exec_command(f"squeue -j {job_id}")
        if stdout.read().decode().strip() == "":  # Job is no longer in queue
            break
        time.sleep(5)  # Poll every 5 seconds
    
    # After the job is complete, download all .vtk files
    return download_vtk_files(ssh)

def download_vtk_files(ssh):
    try:
        # Define the remote and local directories
        local_dir = LOCAL_FILE_DIR
        remote_dir = '/scrfs/storage/prgent/home/'

        # Get the list of all files in the remote directory
        with ssh.open_sftp() as sftp:
            remote_files = sftp.listdir(remote_dir)

            # Filter the .vtk files
            vtk_files = [file for file in remote_files if file.endswith('.vtk')]

            if not vtk_files:
                flash('No .vtk files found on the remote server.', 'error')
                return None

            # Download all .vtk files
            downloaded_files = []
            for vtk_file in vtk_files:
                local_path = os.path.join(local_dir, vtk_file)
                remote_path = os.path.join(remote_dir, vtk_file)
                sftp.get(remote_path, local_path)
                downloaded_files.append(vtk_file)

            return downloaded_files
    
    except Exception as e:
        flash(f"Failed to download .vtk files: {str(e)}", 'error')
        return None


if __name__ == '__main__':
    app.run(debug=True)
