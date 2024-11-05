import paramiko

hostname = 'hpc-portal2.hpc.uark.edu'
username = 'prgent'
password = 'Guitarpicks101'

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    print("Connection successful!")
    # Execute a command
    stdin, stdout, stderr = client.exec_command('ls')
    print(stdout.read().decode())
finally:
    client.close()
