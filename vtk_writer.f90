program vtk_writer
    implicit none
    integer :: i, j, k, nx, ny, nz
    real(8), dimension(:,:,:), allocatable :: u, v, w
    character(len=20) :: filename
    integer :: unit

    ! Grid dimensions
    nx = 10
    ny = 10
    nz = 10

    ! Allocate arrays for velocity components
    allocate(u(nx, ny, nz))
    allocate(v(nx, ny, nz))
    allocate(w(nx, ny, nz))

    ! Fill velocity arrays with sample data (e.g., wind flow)
    do i = 1, nx
        do j = 1, ny
            do k = 1, nz
                u(i,j,k) = sin(2.0d0 * i / nx) * cos(2.0d0 * j / ny)
                v(i,j,k) = sin(2.0d0 * j / ny) * cos(2.0d0 * k / nz)
                w(i,j,k) = cos(2.0d0 * k / nz) * sin(2.0d0 * i / nx)
            end do
        end do
    end do

    ! Write VTK file (ASCII legacy format)
    filename = 'wind_simulation.vtk'
    open(unit=10, file=filename)

    write(10, '(A)') '# vtk DataFile Version 3.0'
    write(10, '(A)') 'Wind velocity data'
    write(10, '(A)') 'ASCII'
    write(10, '(A)') 'DATASET STRUCTURED_POINTS'
    write(10, '(A,I0)') 'DIMENSIONS ', nx, ny, nz
    write(10, '(A,I0,I0,I0)') 'ORIGIN 0 0 0'
    write(10, '(A,I0,I0,I0)') 'SPACING 1 1 1'
    write(10, '(A,I0)') 'POINT_DATA ', nx*ny*nz
    write(10, '(A)') 'VECTORS velocity double'

    ! Write velocity components to file
    do k = 1, nz
        do j = 1, ny
            do i = 1, nx
                write(10, '(3F10.5)') u(i,j,k), v(i,j,k), w(i,j,k)
            end do
        end do
    end do

    close(10)

    ! Deallocate arrays
    deallocate(u)
    deallocate(v)
    deallocate(w)

end program vtk_writer
