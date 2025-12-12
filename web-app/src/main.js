// --- BROWSER IMPORTS ---
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails
} from 'amazon-cognito-identity-js';

// Import CSS
import './style.css';

// --- CONFIGURATION ---
const poolData = {
    UserPoolId: 'us-east-1_lSFojctzR',
    ClientId: '5softmo34b8gmpgg688lhs8kjl'
};

// API CONFIGURATION
const MAIN_API = 'https://qol8fm6q72.execute-api.us-east-1.amazonaws.com/prod';
const PATIENTS_API = 'https://fdnssz2lea.execute-api.us-east-1.amazonaws.com/prod';

const userPool = new CognitoUserPool(poolData);

// --- GLOBAL VARIABLES ---
let currentUser = null;
let idToken = null;
let mediaRecorder = null;
let audioChunks = [];
let selectedPatient = null;

// ============================================
// UI Management
// ============================================
function showScreen(screenId) {
  document.querySelectorAll('.screen').forEach(screen => {
    screen.classList.remove('active');
    screen.classList.add('hidden'); // Ensure others are really hidden
  });

  const screen = document.getElementById(screenId);
  if(screen) {
    screen.classList.remove('hidden');
    screen.classList.add('active');
  }
}

function showLoading(show = true) {
  // Optional: Add a simple spinner logic here if you add a spinner div later
  const status = document.getElementById('recording-status');
  if(status && show) status.textContent = 'Processing...';
}

function showError(elementId, message) {
  const errorEl = document.getElementById(elementId);
  if (!errorEl) return;
  errorEl.textContent = message;
  setTimeout(() => errorEl.textContent = '', 5000);
}

// ============================================
// Authentication Functions
// ============================================
function login(email, password) {
  const authenticationDetails = new AuthenticationDetails({
    Username: email,
    Password: password
  });

  const userData = {
    Username: email,
    Pool: userPool
  };

  const cognitoUser = new CognitoUser(userData);

  cognitoUser.authenticateUser(authenticationDetails, {
    onSuccess: (result) => {
      idToken = result.getIdToken().getJwtToken();
      currentUser = cognitoUser;

      // Update UI with user email
      cognitoUser.getUserAttributes((err, attributes) => {
        if (!err) {
          const emailAttr = attributes.find(attr => attr.Name === 'email');
          const userEmail = emailAttr ? emailAttr.Value : email;
          const emailEl = document.getElementById('user-email');
          if(emailEl) emailEl.textContent = userEmail;
        }
      });

      // ✅ Switch to the Dashboard
      showScreen('dashboard-screen');
    },

    onFailure: (err) => {
      showError('login-error', err.message || 'Login failed');
    },

    newPasswordRequired: (userAttributes, requiredAttributes) => {
      // Handle password change if needed (simplified for now)
      alert('Password change required. Please contact admin.');
    }
  });
}

function logout() {
  if (currentUser) {
    currentUser.signOut();
  }
  currentUser = null;
  idToken = null;
  selectedPatient = null;

  // Reset UI
  const results = document.getElementById('results-panel');
  if(results) results.classList.add('hidden');

  showScreen('login-screen');
}

// ============================================
// Patient Management Functions
// ============================================
async function searchPatients(query) {
  if (!query || query.length < 2) return [];

  try {
    const response = await fetch(
      `${PATIENTS_API}/patients/search?q=${encodeURIComponent(query)}`,
      { headers: { 'Authorization': `Bearer ${idToken}` } }
    );

    if (!response.ok) throw new Error('Search failed');
    const data = await response.json();
    return data.patients || [];
  } catch (error) {
    console.error('Search error:', error);
    return [];
  }
}

async function showPatientResults(query) {
  const resultsDiv = document.getElementById('patient-results');
  if (!resultsDiv) return;

  if (!query || query.length < 2) {
    resultsDiv.style.display = 'none';
    return;
  }

  const patients = await searchPatients(query);
  resultsDiv.innerHTML = '';
  resultsDiv.style.display = 'block';

  // Existing patients
  patients.forEach(patient => {
    const item = document.createElement('div');
    item.className = 'patient-result-item';
    item.innerHTML = `<strong>${patient.name}</strong> <span style="color:#64748b; font-size:0.8em">#${patient.patient_id.substring(0,4)}</span>`;
    item.onclick = () => selectPatient(patient);
    resultsDiv.appendChild(item);
  });

  // Create new option
  const addNew = document.createElement('div');
  addNew.className = 'patient-result-item add-new';
  addNew.innerHTML = `<i class="fa-solid fa-plus"></i> Create: "${query}"`;
  addNew.onclick = () => createNewPatient(query);
  resultsDiv.appendChild(addNew);
}

async function createNewPatient(name) {
  try {
    const response = await fetch(`${PATIENTS_API}/patients`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ name: name.trim() })
    });

    if (!response.ok) throw new Error('Failed to create patient');
    const data = await response.json();
    selectPatient(data.patient);
  } catch (error) {
    alert('Error creating patient: ' + error.message);
  }
}

function selectPatient(patient) {
  selectedPatient = patient;

  const input = document.getElementById('patient-search');
  const results = document.getElementById('patient-results');
  const status = document.getElementById('recording-status');

  if(input) input.value = patient.name;
  if(results) results.style.display = 'none';
  if(status) status.textContent = `Ready to record for ${patient.name}`;
}

// ============================================
// Audio Recording Functions
// ============================================
async function startRecording() {
  if (!selectedPatient) {
    alert('Please select or create a patient first');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000
      }
    });

    const options = { mimeType: 'audio/webm;codecs=opus', bitsPerSecond: 16000 };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      delete options.mimeType; // Fallback
    }

    mediaRecorder = new MediaRecorder(stream, options);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      await transcribeAudio(blob);
      stream.getTracks().forEach(track => track.stop());
    };

    mediaRecorder.start(1000);

    // --- UI UPDATES ---
    const recordBtn = document.getElementById('record-btn');
    const status = document.getElementById('recording-status');
    const resultsPanel = document.getElementById('results-panel');

    // 1. Animate Button
    if(recordBtn) {
      recordBtn.classList.add('recording');
      recordBtn.innerHTML = '<i class="fa-solid fa-stop"></i>'; // Change icon to Stop
    }

    // 2. Update Status Text
    if(status) status.textContent = 'Recording in progress...';

    // 3. ✅ SHOW RESULTS PANEL IMMEDIATELY
    if(resultsPanel) resultsPanel.classList.remove('hidden');

  } catch (error) {
    console.error('Mic Error:', error);
    alert('Could not access microphone. Please allow permissions.');
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();

    const recordBtn = document.getElementById('record-btn');
    const status = document.getElementById('recording-status');

    if(recordBtn) {
      recordBtn.classList.remove('recording');
      recordBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>'; // Change back to Mic
    }

    if(status) status.textContent = 'Processing audio...';
  }
}

// ============================================
// AI Processing
// ============================================
async function transcribeAudio(audioBlob) {
  try {
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);
    await new Promise(resolve => reader.onloadend = resolve);
    const base64Audio = reader.result.split(',')[1];

    const response = await fetch(`${MAIN_API}/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({ audio: base64Audio })
    });

    if (!response.ok) throw new Error('Transcription failed');

    const data = await response.json();
    const transcript = data.transcript;

    // Show Transcript
    const transcriptEl = document.getElementById('transcript');
    if(transcriptEl) transcriptEl.value = transcript;

    // Update Status
    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Generating Clinical Note...';

    await generateVisitSummary(transcript);

  } catch (error) {
    alert('Error: ' + error.message);
    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Error processing audio';
  }
}

async function generateVisitSummary(transcript) {
  try {
    // Get Template Selection
    const templateSelect = document.getElementById('template-select');
    const template = templateSelect ? templateSelect.value : 'soap_general';

    const response = await fetch(`${MAIN_API}/generate-note`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({
        transcript: transcript,
        patient_name: selectedPatient ? selectedPatient.name : 'Unknown',
        patient_id: selectedPatient ? selectedPatient.patient_id : null,
        template: template // Send the selected template
      })
    });

    if (!response.ok) throw new Error('Generation failed');
    const data = await response.json();

    // Show Note
    const soapEl = document.getElementById('soap-note');
    if(soapEl) soapEl.innerHTML = `<pre>${data.note}</pre>`;

    // Final Status
    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Note Generated Successfully';

  } catch (error) {
    const soapEl = document.getElementById('soap-note');
    if(soapEl) soapEl.innerHTML = 'Failed to generate note.';
  }
}

// ============================================
// Initialization & Listeners
// ============================================
document.addEventListener('DOMContentLoaded', () => {

  // Login Button
  const loginBtn = document.getElementById('login-btn');
  if(loginBtn) {
    loginBtn.addEventListener('click', () => {
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      if (email && password) login(email, password);
    });
  }

  // Logout Button
  const logoutBtn = document.getElementById('logout-btn');
  if(logoutBtn) logoutBtn.addEventListener('click', logout);

  // Patient Search Input
  const patientSearch = document.getElementById('patient-search');
  let searchTimeout;
  if(patientSearch) {
    patientSearch.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => showPatientResults(e.target.value), 300);
    });
    // Close results when clicking outside
    document.addEventListener('click', (e) => {
      const results = document.getElementById('patient-results');
      if (results && !e.target.closest('.card-row')) {
        results.style.display = 'none';
      }
    });
  }

  // Record Button (The Big Circle)
  const recordBtn = document.getElementById('record-btn');
  if(recordBtn) {
    recordBtn.addEventListener('click', () => {
      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        startRecording();
      } else {
        stopRecording();
      }
    });
  }

  // Copy Button
  const copyBtn = document.getElementById('copy-btn');
  if(copyBtn) {
    copyBtn.addEventListener('click', () => {
      const note = document.getElementById('soap-note');
      if(note) {
        navigator.clipboard.writeText(note.innerText);
        copyBtn.textContent = 'Copied!';
        setTimeout(() => copyBtn.textContent = 'Copy', 2000);
      }
    });
  }
});