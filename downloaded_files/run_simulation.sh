#!/bin/bash
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
nvfortran -acc -Minfo=accel -fast /scrfs/storage/prgent/home/vtk_writer.f90 -o writer.exe

# Make the executable
chmod +x writer.exe

# Run the simulation
srun --pty ./writer.exe
