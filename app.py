import os
import time
import shutil
import paramiko
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_default_secret_key')

BASE_UPLOAD_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE_DIR = os.path.join(BASE_UPLOAD_DIR, 'downloaded_files')
REMOTE_DIR_TEMPLATE = "/scrfs/storage/{username}/home/"

if not os.path.exists(LOCAL_FILE_DIR):
    os.makedirs(LOCAL_FILE_DIR)

SLURM_SCRIPT_TEMPLATE = """#!/bin/bash
#SBATCH --job-name=test
#SBATCH --output=job_output_%j.log
#SBATCH --nodes=1
#SBATCH --tasks-per-node=1
#SBATCH --time=2:00:00
#SBATCH --partition=cloud72

if [ -f ~/.bash_profile ]; then
    source ~/.bash_profile
fi

module purge
module load nvhpc

cd $SLURM_SUBMIT_DIR
nvfortran -acc -Minfo=accel -fast {remote_dir}vtk_writer.f90 -o writer.exe &> compile_output.log
chmod +x writer.exe
export OMP_NUM_THREADS=2
srun ./writer.exe
mv *.vtk $SLURM_SUBMIT_DIR/ 2>/dev/null || echo "No .vtk files found to move."
echo "Job completed successfully!"
"""

@app.route('/')
def index():
    print("[DEBUG] Rendered index page")
    vtk_files = os.listdir(LOCAL_FILE_DIR)  # List files in the downloaded_files directory
    return render_template('index.html', vtk_files=vtk_files)

@app.route('/upload', methods=['POST'])
def upload_and_submit():
    print("[DEBUG] Received /upload request")
    username = request.form.get('username')
    password = request.form.get('password')
    files = request.files.getlist('files')

    if not username or not password:
        print("[ERROR] Username or password missing")
        return jsonify({'status': 'error', 'message': 'Username and password are required.'}), 400

    if not files:
        print("[ERROR] No files uploaded")
        return jsonify({'status': 'error', 'message': 'No files uploaded.'}), 400

    remote_dir = REMOTE_DIR_TEMPLATE.format(username=username)
    print(f"[DEBUG] Remote directory for user {username}: {remote_dir}")

    # Save files locally
    saved_files = save_files(files)
    print(f"[DEBUG] Saved files: {saved_files}")

    if not saved_files:
        print("[ERROR] Failed to save uploaded files")
        return jsonify({'status': 'error', 'message': 'Failed to save uploaded files.'}), 500

    # Establish SSH connection
    ssh = establish_ssh_connection(username, password)
    if ssh is None:
        print("[ERROR] SSH connection failed")
        return jsonify({'status': 'error', 'message': 'SSH connection failed.'}), 500

    try:
        # Upload files and Slurm script
        for local_file in saved_files:
            print(f"[DEBUG] Uploading file: {local_file}")
            upload_file(ssh, local_file, os.path.join(remote_dir, os.path.basename(local_file)))

        # Create and submit the Slurm script
        slurm_script = SLURM_SCRIPT_TEMPLATE.format(remote_dir=remote_dir)
        print(f"[DEBUG] Generated Slurm script:\n{slurm_script}")
        job_id = submit_slurm_script(ssh, slurm_script, remote_dir)

        if job_id:
            print(f"[DEBUG] Job submitted with ID: {job_id}")
            # Poll for job completion
            poll_for_job_completion(ssh, username, job_id)

            # Retrieve .vtk files
            print("[DEBUG] Retrieving .vtk files")
            vtk_files = retrieve_vtk_files(ssh, remote_dir)

            if vtk_files:
                print(f"[DEBUG] Retrieved .vtk files: {vtk_files}")
                return jsonify({'status': 'success', 'message': 'Job completed and .vtk files retrieved.', 'vtk_files': vtk_files}), 200
            else:
                print("[DEBUG] No .vtk files found.")
                return jsonify({'status': 'success', 'message': 'Job completed, but no .vtk files found.'}), 200
        else:
            print("[ERROR] Failed to submit the Slurm job")
            return jsonify({'status': 'error', 'message': 'Failed to submit the Slurm job.'}), 500
    finally:
        ssh.close()
        print("[DEBUG] SSH connection closed")

def save_files(files):
    saved_files = []
    for file in files:
        if file and file.filename:
            file_path = os.path.join(LOCAL_FILE_DIR, file.filename)
            try:
                print(f"[DEBUG] Saving file locally: {file.filename}")
                file.save(file_path)
                saved_files.append(file_path)
            except Exception as e:
                print(f"[ERROR] Error saving file {file.filename}: {str(e)}")
    return saved_files

def establish_ssh_connection(username, password):
    try:
        print(f"[DEBUG] Establishing SSH connection for user {username}")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('hpc-portal2.hpc.uark.edu', username=username, password=password)
        print("[DEBUG] SSH connection established")
        return ssh
    except Exception as e:
        print(f"[ERROR] SSH connection failed: {str(e)}")
        return None

def upload_file(ssh, local_path, remote_path):
    try:
        print(f"[DEBUG] Uploading file {local_path} to {remote_path}")
        with ssh.open_sftp() as sftp:
            sftp.put(local_path, remote_path)
    except Exception as e:
        print(f"[ERROR] Error uploading {local_path}: {str(e)}")

def submit_slurm_script(ssh, slurm_script, remote_dir):
    remote_script_path = os.path.join(remote_dir, "run_simulation.sh")
    try:
        print(f"[DEBUG] Writing Slurm script to {remote_script_path}")
        with ssh.open_sftp() as sftp:
            with sftp.file(remote_script_path, "w") as script_file:
                script_file.write(slurm_script)
        ssh.exec_command(f"dos2unix {remote_script_path}")
        ssh.exec_command(f"chmod +x {remote_script_path}")
        stdin, stdout, stderr = ssh.exec_command(f"sbatch {remote_script_path}")
        output = stdout.read().decode().strip()
        print(f"[DEBUG] Slurm submission output: {output}")
        if "Submitted batch job" in output:
            return output.split()[-1]
    except Exception as e:
        print(f"[ERROR] Error submitting Slurm script: {str(e)}")
    return None

def poll_for_job_completion(ssh, username, job_id):
    print(f"[DEBUG] Polling for job completion. Job ID: {job_id}")
    try:
        while True:
            stdin, stdout, stderr = ssh.exec_command(f"squeue -u {username} -j {job_id}")
            output = stdout.read().decode().strip()
            print(f"[DEBUG] squeue output: {output}")
            if job_id not in output:
                print("[DEBUG] Job completed!")
                break
            time.sleep(5)  # Poll every 5 seconds
    except Exception as e:
        print(f"[ERROR] Error polling job status: {str(e)}")

def retrieve_vtk_files(ssh, remote_dir):
    vtk_files = []
    try:
        print(f"[DEBUG] Checking for .vtk files in remote directory: {remote_dir}")
        with ssh.open_sftp() as sftp:
            file_list = sftp.listdir(remote_dir)
            print(f"[DEBUG] Files in remote directory: {file_list}")
            
            vtk_files = [file for file in file_list if file.endswith('.vtk')]

            if not vtk_files:
                print("[DEBUG] No .vtk files found in the remote directory.")
                return vtk_files

            for vtk_file in vtk_files:
                remote_path = os.path.join(remote_dir, vtk_file)
                local_path = os.path.join(LOCAL_FILE_DIR, vtk_file)
                print(f"[DEBUG] Downloading {vtk_file} to {local_path}")
                
                # Retrieve the .vtk file from the remote server
                sftp.get(remote_path, local_path)
                print(f"[DEBUG] {vtk_file} successfully downloaded.")
                
    except Exception as e:
        print(f"[ERROR] Error retrieving .vtk files: {str(e)}")
    
    return vtk_files

if __name__ == '__main__':
    app.run(debug=True)
