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

// ⚠️ FIXED: Define API URLs directly (Replaces AWS_CONFIG)
const MAIN_API = 'https://qol8fm6q72.execute-api.us-east-1.amazonaws.com/prod';
const PATIENTS_API = 'https://fdnssz2lea.execute-api.us-east-1.amazonaws.com/prod';

const userPool = new CognitoUserPool(poolData);

// --- GLOBAL VARIABLES ---
let currentUser = null;
let idToken = null;
let mediaRecorder = null;
let audioChunks = [];
let userRole = 'user';
let selectedPatient = null;
let audioContext = null;
let analyser = null;
let microphone = null;
let testStream = null;
let animationId = null;

// ============================================
// UI Management
// ============================================
function showScreen(screenId) {
  document.querySelectorAll('.screen').forEach(screen => {
    screen.classList.remove('active');
  });
  const screen = document.getElementById(screenId);
  if(screen) screen.classList.add('active');
}

function showView(viewId) {
  document.querySelectorAll('.view').forEach(view => {
    view.classList.remove('active');
  });

  const view = document.getElementById(`${viewId}-view`);
  if(view) view.classList.add('active');

  // Update nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  const navItem = document.getElementById(`nav-${viewId}`);
  if(navItem) navItem.classList.add('active');

  // Load microphones when entering audio test view
  if (viewId === 'audio-test') {
    loadMicrophones();
  }

  closeSidebar();
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if(sidebar) sidebar.classList.toggle('open');
  if(overlay) overlay.classList.toggle('active');
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if(sidebar) sidebar.classList.remove('open');
  if(overlay) overlay.classList.remove('active');
}

function showLoading(show = true) {
  const loading = document.getElementById('loading');
  if (!loading) return;
  if (show) {
    loading.classList.add('show');
  } else {
    loading.classList.remove('show');
  }
}

function showError(elementId, message) {
  const errorEl = document.getElementById(elementId);
  if (!errorEl) return;
  errorEl.textContent = message;
  errorEl.classList.add('show');
  setTimeout(() => errorEl.classList.remove('show'), 5000);
}

// ============================================
// Authentication Functions
// ============================================
function login(email, password) {
  showLoading();

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
      showLoading(false);
      idToken = result.getIdToken().getJwtToken();
      currentUser = cognitoUser;

      cognitoUser.getUserAttributes((err, attributes) => {
        if (!err) {
          const nameAttr = attributes.find(attr => attr.Name === 'name');
          const emailAttr = attributes.find(attr => attr.Name === 'email');
          const userName = nameAttr ? nameAttr.Value : email;
          const userEmail = emailAttr ? emailAttr.Value : email;

          // Safe DOM updates
          const sidebarName = document.getElementById('sidebar-user-name');
          const sidebarEmail = document.getElementById('sidebar-user-email');
          if(sidebarName) sidebarName.textContent = userName;
          if(sidebarEmail) sidebarEmail.textContent = userEmail;
        }
      });

      showScreen('main-screen');
      showView('visit');
      loadHistory();
      // checkAdminAccess(); // Disabled until admin routes are fully fixed
    },

    onFailure: (err) => {
      showLoading(false);
      showError('login-error', err.message || 'Login failed');
    },

    newPasswordRequired: (userAttributes, requiredAttributes) => {
      showLoading(false);
      currentUser = cognitoUser;
      showScreen('password-change-screen');
    }
  });
}

function changePassword(newPassword) {
  if (!currentUser) {
    showError('password-error', 'Session expired. Please login again.');
    return;
  }

  showLoading();

  currentUser.completeNewPasswordChallenge(newPassword, {}, {
    onSuccess: (result) => {
      showLoading(false);
      idToken = result.getIdToken().getJwtToken();
      showScreen('main-screen');
      showView('visit');
      loadHistory();
    },
    onFailure: (err) => {
      showLoading(false);
      showError('password-error', err.message || 'Password change failed');
    }
  });
}

function logout() {
  if (currentUser) {
    currentUser.signOut();
  }
  currentUser = null;
  idToken = null;
  userRole = 'user';
  selectedPatient = null;
  clearVisit();
  showScreen('login-screen');
}

// ============================================
// Patient Management Functions
// ============================================
async function searchPatients(query) {
  if (!query || query.length < 2) {
    return [];
  }

  try {
    const response = await fetch(
      `${PATIENTS_API}/patients/search?q=${encodeURIComponent(query)}`,
      {
        headers: { 'Authorization': `Bearer ${idToken}` }
      }
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

  // Show existing patients
  patients.forEach(patient => {
    const item = document.createElement('div');
    item.className = 'patient-result-item';
    item.innerHTML = `
      <div style="font-weight: 600;">${patient.name}</div>
      <div style="font-size: 12px; color: var(--text-gray);">
        ID: ${patient.patient_id.substring(0, 8)}
      </div>
    `;
    item.onclick = () => selectPatient(patient);
    resultsDiv.appendChild(item);
  });

  // Add "Create new patient" option
  const addNew = document.createElement('div');
  addNew.className = 'patient-result-item add-new';
  addNew.innerHTML = `<strong>➕ Create new patient:</strong> "${query}"`;
  addNew.onclick = () => createNewPatient(query);
  resultsDiv.appendChild(addNew);
}

async function createNewPatient(name) {
  showLoading();

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
    showLoading(false);
    selectPatient(data.patient);

  } catch (error) {
    showLoading(false);
    alert('Error creating patient: ' + error.message);
  }
}

function selectPatient(patient) {
  selectedPatient = patient;
  const input = document.getElementById('patient-search');
  if(input) input.value = patient.name;

  const results = document.getElementById('patient-results');
  const clearBtn = document.getElementById('patient-clear');
  const recordBtn = document.getElementById('record-btn');
  const prompt = document.getElementById('capture-prompt');

  if(results) results.style.display = 'none';
  if(clearBtn) clearBtn.style.display = 'block';
  if(recordBtn) recordBtn.disabled = false;

  if(prompt) {
    prompt.innerHTML = `
      <span class="prompt-icon">✓</span>
      <h3>${patient.name}</h3>
      <p>Ready to capture conversation</p>
    `;
  }
}

function clearPatient() {
  selectedPatient = null;
  const input = document.getElementById('patient-search');
  const results = document.getElementById('patient-results');
  const clearBtn = document.getElementById('patient-clear');
  const recordBtn = document.getElementById('record-btn');
  const prompt = document.getElementById('capture-prompt');

  if(input) input.value = '';
  if(results) results.style.display = 'none';
  if(clearBtn) clearBtn.style.display = 'none';
  if(recordBtn) recordBtn.disabled = true;

  if(prompt) {
    prompt.innerHTML = `
      <span class="prompt-icon">👤</span>
      <h3>Select or add a patient to begin</h3>
      <p>Search by name or create a new patient record.</p>
    `;
  }
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
    const constraints = {
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000
      }
    };

    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    const options = {
      mimeType: 'audio/webm;codecs=opus',
      bitsPerSecond: 16000
    };

    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      console.warn(`${options.mimeType} not supported, falling back to default`);
      delete options.mimeType;
    }

    mediaRecorder = new MediaRecorder(stream, options);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const blobType = mediaRecorder.mimeType || 'audio/webm';
      const audioBlob = new Blob(audioChunks, { type: blobType });

      console.log(`Audio Size: ${(audioBlob.size / 1024).toFixed(2)} KB`);

      await transcribeAudio(audioBlob);
      stream.getTracks().forEach(track => track.stop());
    };

    mediaRecorder.start(1000);

    const recordBtn = document.getElementById('record-btn');
    const recordText = document.getElementById('record-text');
    const status = document.getElementById('recording-status');

    if(recordBtn) recordBtn.classList.add('recording');
    if(recordText) recordText.textContent = 'End Conversation';
    if(status) status.textContent = '🔴 Recording in progress...';

  } catch (error) {
    console.error('Error accessing microphone:', error);
    alert('Could not access microphone. Please check permissions.');
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();

    const recordBtn = document.getElementById('record-btn');
    const recordText = document.getElementById('record-text');
    const status = document.getElementById('recording-status');

    if(recordBtn) recordBtn.classList.remove('recording');
    if(recordText) recordText.textContent = 'Start Conversation';
    if(status) status.textContent = 'Processing audio...';
  }
}

// ============================================
// Transcription Functions
// ============================================
async function transcribeAudio(audioBlob) {
  showLoading();

  try {
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);

    await new Promise((resolve) => {
      reader.onloadend = resolve;
    });

    const base64Audio = reader.result.split(',')[1];

    const response = await fetch(`${MAIN_API}/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({
        audio: base64Audio
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Transcription failed');
    }

    const data = await response.json();
    const transcript = data.transcript;

    if (!transcript || transcript.trim() === '') {
      throw new Error('No speech detected. Please try again.');
    }

    const transcriptEl = document.getElementById('transcript');
    const status = document.getElementById('recording-status');
    const results = document.getElementById('results-section');

    if(transcriptEl) transcriptEl.value = transcript;
    if(status) status.textContent = '✓ Transcription complete';
    if(results) results.style.display = 'block';

    await generateVisitSummary(transcript);

  } catch (error) {
    console.error('Transcription error:', error);
    showLoading(false);
    const status = document.getElementById('recording-status');
    if(status) status.textContent = '✗ Transcription failed: ' + error.message;
    alert('Transcription failed: ' + error.message);
  }
}

// ============================================
// Visit Summary Generation
// ============================================
async function generateVisitSummary(transcript) {
  try {
    const patientName = selectedPatient ? selectedPatient.name : 'Unknown';
    const patientId = selectedPatient ? selectedPatient.patient_id : null;

    const response = await fetch(`${MAIN_API}/generate-note`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${idToken}`
      },
      body: JSON.stringify({
        transcript: transcript,
        patient_name: patientName,
        patient_id: patientId
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to generate summary');
    }

    const data = await response.json();

    const soapNoteEl = document.getElementById('soap-note');
    if(soapNoteEl) soapNoteEl.innerHTML = `<pre>${data.note}</pre>`;

    const status = document.getElementById('recording-status');
    if(status) status.textContent = '✓ Visit summary generated and saved';

    showLoading(false);
    switchTab('note');
    await loadHistory();

  } catch (error) {
    console.error('Summary generation error:', error);
    showLoading(false);
    const status = document.getElementById('recording-status');
    if(status) status.textContent = '✗ Generation failed: ' + error.message;
    alert('Failed to generate summary: ' + error.message);
  }
}

// ============================================
// Tab Switching
// ============================================
function switchTab(tabName) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
  if(activeBtn) activeBtn.classList.add('active');

  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.remove('active');
  });
  const activeContent = document.getElementById(`${tabName}-tab`);
  if(activeContent) activeContent.classList.add('active');
}

// ============================================
// History & Notes
// ============================================
async function loadHistory() {
  try {
    const response = await fetch(`${MAIN_API}/notes?limit=20`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${idToken}`
      }
    });

    if (!response.ok) throw new Error('Failed to load history');

    const data = await response.json();
    const historyList = document.getElementById('history-list');
    if(!historyList) return;

    if (data.notes && data.notes.length > 0) {
      historyList.innerHTML = '';
      data.notes.forEach(note => {
        const noteEl = document.createElement('div');
        noteEl.className = 'history-item';
        noteEl.innerHTML = `
          <div class="timestamp">${new Date(note.timestamp).toLocaleString()}</div>
          <div class="patient">Patient: ${note.patient_name || 'Unknown'}</div>
          <div class="preview">${note.soap_note.substring(0, 100)}...</div>
        `;
        noteEl.onclick = () => viewNote(note);
        historyList.appendChild(noteEl);
      });
    } else {
      historyList.innerHTML = '<p style="color: var(--text-gray); text-align: center; padding: 40px;">No notes yet</p>';
    }

  } catch (error) {
    console.error('Error loading history:', error);
  }
}

function viewNote(note) {
  showView('visit');

  const transcriptEl = document.getElementById('transcript');
  const soapEl = document.getElementById('soap-note');
  const results = document.getElementById('results-section');
  const prompt = document.getElementById('capture-prompt');

  if(transcriptEl) transcriptEl.value = note.transcript || 'No transcript available';
  if(soapEl) soapEl.innerHTML = `<pre>${note.soap_note}</pre>`;
  if(results) results.style.display = 'block';

  if (note.patient_name && prompt) {
    prompt.innerHTML = `
      <span class="prompt-icon">📄</span>
      <h3>${note.patient_name}</h3>
      <p>Viewing past visit from ${new Date(note.timestamp).toLocaleDateString()}</p>
    `;
  }

  switchTab('note');
}

function copyToClipboard() {
  const soapNote = document.getElementById('soap-note');
  if(!soapNote) return;

  const soapText = soapNote.innerText;
  navigator.clipboard.writeText(soapText).then(() => {
    const copyBtn = document.getElementById('copy-btn');
    const originalText = copyBtn.textContent;
    copyBtn.textContent = '✓ Copied!';
    setTimeout(() => {
      copyBtn.textContent = originalText;
    }, 2000);
  });
}

function clearVisit() {
  clearPatient();
  const results = document.getElementById('results-section');
  const transcript = document.getElementById('transcript');
  const soap = document.getElementById('soap-note');
  const status = document.getElementById('recording-status');

  if(results) results.style.display = 'none';
  if(transcript) transcript.value = '';
  if(soap) soap.innerHTML = '<p class="placeholder">Visit summary will appear here...</p>';
  if(status) status.textContent = '';
}

// ============================================
// Event Listeners
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  // Login
  const loginBtn = document.getElementById('login-btn');
  if(loginBtn) {
    loginBtn.addEventListener('click', () => {
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;

      if (!email || !password) {
        showError('login-error', 'Please enter email and password');
        return;
      }
      login(email, password);
    });
  }

  const pwInput = document.getElementById('password');
  if(pwInput) {
    pwInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        const btn = document.getElementById('login-btn');
        if(btn) btn.click();
      }
    });
  }

  // Sidebar
  const menuToggle = document.getElementById('menu-toggle');
  const sidebarClose = document.getElementById('sidebar-close');
  const overlay = document.getElementById('sidebar-overlay');
  const logoutBtn = document.getElementById('sidebar-logout');

  if(menuToggle) menuToggle.addEventListener('click', toggleSidebar);
  if(sidebarClose) sidebarClose.addEventListener('click', closeSidebar);
  if(overlay) overlay.addEventListener('click', closeSidebar);
  if(logoutBtn) logoutBtn.addEventListener('click', logout);

  // Navigation
  const navHome = document.getElementById('nav-home');
  const navHistory = document.getElementById('nav-history');

  if(navHome) navHome.addEventListener('click', (e) => {
    e.preventDefault();
    showView('visit');
  });

  if(navHistory) navHistory.addEventListener('click', (e) => {
    e.preventDefault();
    showView('history');
  });

  // Patient Search
  const patientSearch = document.getElementById('patient-search');
  let searchTimeout;

  if(patientSearch) {
    patientSearch.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        showPatientResults(e.target.value);
      }, 300);
    });

    patientSearch.addEventListener('focus', (e) => {
      if (e.target.value.length >= 2) {
        showPatientResults(e.target.value);
      }
    });
  }

  const patientClear = document.getElementById('patient-clear');
  if(patientClear) patientClear.addEventListener('click', clearPatient);

  // Close search results on click outside
  document.addEventListener('click', (e) => {
    const results = document.getElementById('patient-results');
    if (results && !e.target.closest('.patient-selector-container')) {
      results.style.display = 'none';
    }
  });

  // Recording
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

  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.getAttribute('data-tab'));
    });
  });

  // Copy
  const copyBtn = document.getElementById('copy-btn');
  if(copyBtn) copyBtn.addEventListener('click', copyToClipboard);
});