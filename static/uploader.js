let dropArea = document.getElementById('drop-area');
let outputList = document.getElementById('output-list');
let feedback = document.getElementById('feedback');
let logsContainer = document.getElementById('logs'); // Container for logs

// Prevent default behaviors for drag and drop
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

// Highlight the drop area when file is dragged over
dropArea.addEventListener('dragenter', highlightDropArea, false);
dropArea.addEventListener('dragover', highlightDropArea, false);

// Remove highlight when file leaves drop area or is dropped
dropArea.addEventListener('dragleave', unhighlightDropArea, false);
dropArea.addEventListener('drop', unhighlightDropArea, false);

// Handle the drop event
dropArea.addEventListener('drop', handleDrop, false);

// Handle file selection through the input button
document.getElementById('fileElem').addEventListener('change', function (e) {
    let files = e.target.files;
    handleFiles(files);
});

// Prevent default behavior for drag and drop events
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Highlight the drop area
function highlightDropArea() {
    dropArea.classList.add('highlight');
}

// Remove highlight from the drop area
function unhighlightDropArea() {
    dropArea.classList.remove('highlight');
}

// Handle dropped files
function handleDrop(e) {
    let dt = e.dataTransfer;
    let files = dt.files;
    handleFiles(files);
}

// Handle files dropped or selected
function handleFiles(files) {
    if (files.length === 0) {
        feedback.textContent = 'No files selected.';
        feedback.style.color = 'red';
        return;
    }

    let formData = new FormData();

    // Get credentials from the form
    let username = document.getElementById('username').value.trim();
    let password = document.getElementById('password').value.trim();

    // Validate credentials
    if (!username || !password) {
        feedback.textContent = 'Please enter both username and password.';
        feedback.style.color = 'red';
        return;
    }

    // Add credentials to FormData
    formData.append('username', username);
    formData.append('password', password);

    // Append each file to the FormData
    [...files].forEach(file => {
        console.log(`Appending file: ${file.name}`);
        formData.append('files', file);
    });

    feedback.textContent = 'Uploading files...';
    feedback.style.color = 'blue';

    // Send the files and credentials to the Flask backend
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                console.error('Server error:', response.status);
                return response.json().then(err => {
                    throw new Error(err.message || 'Network response was not ok');
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Server response:', data);

            if (data.status === 'success') {
                let vtkFiles = data.vtk_files; // Access the list of VTK files from the backend
                if (vtkFiles && vtkFiles.length > 0) {
                    displayVTKFiles(vtkFiles); // Display the list of VTK files
                    feedback.textContent = 'Upload and execution successful!';
                    feedback.style.color = 'green';
                } else {
                    feedback.textContent = 'No VTK files returned from the server.';
                    feedback.style.color = 'orange';
                }
            } else {
                throw new Error(data.message || 'Upload failed.');
            }
        })
        .catch(err => {
            feedback.textContent = `Upload failed: ${err.message}`;
            feedback.style.color = 'red';
            console.error('Error:', err);
        });
}

// Display the list of VTK files
function displayVTKFiles(files) {
    outputList.innerHTML = ''; // Clear previous outputs
    files.forEach(file => {
        console.log(`Adding VTK file to the output list: ${file}`);
        let li = document.createElement('li');
        let link = document.createElement('a');
        link.href = `/downloaded_files/${file}`; // Adjust this to point to the download route in your Flask app
        link.innerText = file;
        link.target = '_blank'; // Open in a new tab
        li.appendChild(link);
        outputList.appendChild(li);
    });
}

// Append logs to the logs container
function appendLog(log) {
    let logItem = document.createElement('div');
    logItem.textContent = log;
    logsContainer.appendChild(logItem);
    logsContainer.scrollTop = logsContainer.scrollHeight; // Scroll to the latest log
}
