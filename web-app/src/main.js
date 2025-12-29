// --- BROWSER IMPORTS ---
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails
} from 'amazon-cognito-identity-js';

// Import CSS
import './style.css';
import { config } from './config.js';

const poolData = {
  UserPoolId: config.userPoolId,
  ClientId: config.clientId
};

const MAIN_API = config.apiEndpoint;
const PATIENTS_API = config.apiEndpoint;

const userPool = new CognitoUserPool(poolData);

// --- GLOBAL VARIABLES ---
let currentUser = null;
let idToken = null;
let userRole = 'user';
let userEmail = '';
let mediaRecorder = null;
let audioChunks = [];
let selectedPatient = null;
let resetEmail = null;
let templatesCache = [];
let visitsCache = [];
let editingTemplateId = null;
let selectedMicId = null;
let micTestStream = null;
let micAnalyser = null;
let micAnimationFrame = null;

// Quick mic check variables
let quickMicStream = null;
let quickMicAnalyser = null;
let quickMicAnimation = null;

// ============================================
// UI Management
// ============================================
function isMobile() {
  return window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
}
function showScreen(screenId) {
  console.log("🔄 showScreen called with:", screenId);

  // Hide all screens first
  document.querySelectorAll('.screen').forEach(screen => {
    screen.classList.remove('active');
    screen.classList.add('hidden');
  });

  // Show the requested screen
  const screen = document.getElementById(screenId);
  if(screen) {
    screen.classList.remove('hidden');
    screen.classList.add('active');
  } else {
    console.error("❌ Screen not found:", screenId);
  }
}

function showView(viewId) {
  console.log("🔄 showView called with:", viewId);

  // Update nav items
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
    if(item.dataset.view === viewId) {
      item.classList.add('active');
    }
  });

  // Hide all views
  document.querySelectorAll('.view').forEach(view => {
    view.classList.remove('active');
    view.classList.add('hidden');
  });

  // Show the requested view
  const view = document.getElementById(`view-${viewId}`);
  if(view) {
    view.classList.remove('hidden');
    view.classList.add('active');

    // Load data for specific views
    if(viewId === 'visits') {
      loadVisits();
    } else if(viewId === 'templates') {
      loadTemplates();
    } else if(viewId === 'settings') {
      loadSettings();
    } else if(viewId === 'scribe') {
      loadTemplateDropdown();
    } else if(viewId === 'invite') {
      loadTeamMembers();
    }
  }
}

function showError(elementId, message) {
  const errorEl = document.getElementById(elementId);
  if (!errorEl) return;
  errorEl.textContent = message;
  setTimeout(() => errorEl.textContent = '', 5000);
}

function showSuccess(elementId, message) {
  const successEl = document.getElementById(elementId);
  if (!successEl) return;
  successEl.textContent = message;
}

// ============================================
// Authentication Functions
// ============================================
function login(email, password) {
  console.log("🔐 Attempting Login for:", email); // DEBUG

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
      console.log("✅ Login Successful!");

      idToken = result.getIdToken().getJwtToken();

      // --- DEBUGGING TOKEN ---
      window.idToken = idToken;
      console.log("🔑 Token Received (First 20 chars):", idToken.substring(0, 20) + "...");
      console.log("🔑 Token Type:", typeof idToken);
      // ----------------------

      currentUser = cognitoUser;

      // Decode JWT to get role
      const payload = JSON.parse(atob(idToken.split('.')[1]));
      const groups = payload['cognito:groups'] || [];
      userRole = Array.isArray(groups) && groups.includes('Admin') ? 'admin' : 'user';
      userEmail = payload.email || email;

      console.log("User role:", userRole);
      console.log("User email:", userEmail);

      // Update UI with user info
      updateUserDisplay();

      // Show admin features if admin
      if(userRole === 'admin') {
        document.querySelectorAll('.admin-only').forEach(el => {
          el.style.display = 'flex';
        });
      }

      // Switch to dashboard
      showScreen('dashboard-screen');
      showView('scribe');

      // Show quick mic check popup after short delay
      setTimeout(() => showQuickMicCheck(), 500);
    },

    onFailure: (err) => {
      console.error("Login Failed:", err);
      showError('login-error', err.message || 'Login failed');
    },

    newPasswordRequired: (userAttributes, requiredAttributes) => {
      alert('Password change required. Please contact admin.');
    }
  });
}

function logout() {
  console.log("👋 Logging out..."); // DEBUG
  if (currentUser) {
    currentUser.signOut();
  }
  currentUser = null;
  idToken = null;
  userRole = 'user';
  userEmail = '';
  selectedPatient = null;
  templatesCache = [];
  visitsCache = [];

  // Hide admin features
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = 'none';
  });

  // Reset UI
  const results = document.getElementById('results-panel');
  if(results) results.classList.add('hidden');

  showScreen('login-screen');
}

function updateUserDisplay() {
  const sidebarEmail = document.getElementById('sidebar-user-email');
  const sidebarRole = document.getElementById('sidebar-user-role');
  const settingsEmail = document.getElementById('settings-email');
  const settingsRole = document.getElementById('settings-role');

  if(sidebarEmail) sidebarEmail.textContent = userEmail;
  if(sidebarRole) sidebarRole.textContent = userRole === 'admin' ? 'Administrator' : 'User';
  if(settingsEmail) settingsEmail.value = userEmail;
  if(settingsRole) settingsRole.value = userRole === 'admin' ? 'Administrator' : 'User';
}

// ============================================
// Forgot Password Functions
// ============================================
function initiateForgotPassword(email) {
  if (!email || !email.trim()) {
    showError('forgot-error', 'Please enter your email address');
    return;
  }

  const userData = {
    Username: email.trim(),
    Pool: userPool
  };

  const cognitoUser = new CognitoUser(userData);
  resetEmail = email.trim();

  cognitoUser.forgotPassword({
    onSuccess: (data) => {
      console.log('✅ Verification code sent:', data);
      showScreen('reset-password-screen');
    },
    onFailure: (err) => {
      console.error('❌ Forgot password error:', err);
      showError('forgot-error', err.message || 'Failed to send verification code');
    }
  });
}

function confirmNewPassword(verificationCode, newPassword, confirmPassword) {
  if (!verificationCode || !verificationCode.trim()) {
    showError('reset-error', 'Please enter the verification code');
    return;
  }

  if (!newPassword || newPassword.length < 8) {
    showError('reset-error', 'Password must be at least 8 characters');
    return;
  }

  if (newPassword !== confirmPassword) {
    showError('reset-error', 'Passwords do not match');
    return;
  }

  if (!resetEmail) {
    showError('reset-error', 'Session expired. Please start over.');
    showScreen('forgot-password-screen');
    return;
  }

  const userData = {
    Username: resetEmail,
    Pool: userPool
  };

  const cognitoUser = new CognitoUser(userData);

  cognitoUser.confirmPassword(verificationCode.trim(), newPassword, {
    onSuccess: () => {
      console.log('✅ Password reset successful!');
      showSuccess('reset-success', 'Password reset successful! Redirecting to login...');

      resetEmail = null;

      document.getElementById('verification-code').value = '';
      document.getElementById('new-password').value = '';
      document.getElementById('confirm-password').value = '';

      setTimeout(() => {
        showScreen('login-screen');
        const successEl = document.getElementById('reset-success');
        if (successEl) successEl.textContent = '';
      }, 2000);
    },
    onFailure: (err) => {
      console.error('❌ Password reset failed:', err);
      showError('reset-error', err.message || 'Failed to reset password');
    }
  });
}

// ============================================
// Change Password (from Settings)
// ============================================
function changePassword(currentPassword, newPassword, confirmPassword) {
  if (!currentPassword) {
    showError('password-change-error', 'Please enter your current password');
    return;
  }

  if (!newPassword || newPassword.length < 8) {
    showError('password-change-error', 'New password must be at least 8 characters');
    return;
  }

  if (newPassword !== confirmPassword) {
    showError('password-change-error', 'New passwords do not match');
    return;
  }

  if (!currentUser) {
    showError('password-change-error', 'Not logged in');
    return;
  }

  currentUser.changePassword(currentPassword, newPassword, (err, result) => {
    if (err) {
      console.error('Password change error:', err);
      showError('password-change-error', err.message || 'Failed to change password');
    } else {
      console.log('Password changed successfully');
      showSuccess('password-change-success', 'Password changed successfully!');

      // Clear fields
      document.getElementById('current-password').value = '';
      document.getElementById('settings-new-password').value = '';
      document.getElementById('settings-confirm-password').value = '';
    }
  });
}

// ============================================
// Templates Functions
// ============================================
async function loadTemplates() {
  // --- DEBUG ---
  console.log("📡 Fetching Templates...");
  console.log("   Token Status:", idToken ? "Exists" : "MISSING");
  // --- DEBUG ---

  const list = document.getElementById('templates-list');
  if(!list) return;

  list.innerHTML = `
    <div class="loading-spinner">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading templates...</span>
    </div>
  `;

  try {
    const response = await fetch(`${MAIN_API}/templates`, {
      headers: { 'Authorization': idToken }
    });

    if (!response.ok) throw new Error('Failed to load templates');

    const data = await response.json();
    templatesCache = data.templates || [];

    renderTemplates();
  } catch (error) {
    console.error('Error loading templates:', error);

    // Show default templates if API fails
    templatesCache = getDefaultTemplates();
    renderTemplates();
  }
}

function getDefaultTemplates() {
  return [
    {
      template_id: 'default_soap',
      name: 'SOAP General',
      description: 'Standard SOAP format for general dentistry visits',
      is_default: true,
      example_output: `SUBJECTIVE:
Patient presents for [reason]. Reports [symptoms/concerns].

OBJECTIVE:
Exam findings: [clinical observations]
Teeth examined: [tooth numbers]
Radiographs: [if applicable]

ASSESSMENT:
[Diagnosis and clinical impression]

PLAN:
1. [Treatment performed]
2. [Follow-up recommendations]
3. [Next appointment]`
    },
    {
      template_id: 'default_hygiene',
      name: 'Hygiene Recall',
      description: 'Template for routine cleaning and hygiene visits',
      is_default: true,
      example_output: `SUBJECTIVE:
Patient presents for routine prophylaxis. [Any concerns reported]

OBJECTIVE:
Probing depths: [findings]
Bleeding on probing: [yes/no, locations]
Plaque score: [percentage]
Calculus: [light/moderate/heavy]

ASSESSMENT:
[Periodontal status]

PLAN:
1. Prophylaxis completed
2. Fluoride treatment: [yes/no]
3. OHI provided
4. Return in [timeframe]`
    }
  ];
}

function renderTemplates() {
  const list = document.getElementById('templates-list');
  if(!list) return;

  if(templatesCache.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-file-lines"></i>
        <p>No templates yet. Create your first template!</p>
      </div>
    `;
    return;
  }

  list.innerHTML = templatesCache.map(template => `
    <div class="template-card" data-id="${template.template_id}">
      <div class="template-card-header">
        <span class="template-name">${template.name}</span>
        <span class="template-badge ${template.is_default ? 'default' : 'custom'}">
          ${template.is_default ? 'Default' : 'Custom'}
        </span>
      </div>
      <p class="template-description">${template.description || 'No description'}</p>
      <div class="template-preview">${template.example_output || ''}</div>
      <div class="template-actions">
        <button class="btn-edit" onclick="editTemplate('${template.template_id}')">
          <i class="fa-solid fa-pen"></i> Edit
        </button>
        ${!template.is_default ? `
          <button class="btn-delete" onclick="deleteTemplate('${template.template_id}')">
            <i class="fa-solid fa-trash"></i> Delete
          </button>
        ` : ''}
      </div>
    </div>
  `).join('');
}

async function loadTemplateDropdown() {
  const select = document.getElementById('template-select');
  if(!select) return;

  try {
    const response = await fetch(`${MAIN_API}/templates`, {
      headers: { 'Authorization': idToken }
    });

    if (!response.ok) throw new Error('Failed to load templates');

    const data = await response.json();
    const templates = data.templates || getDefaultTemplates();

    select.innerHTML = templates.map(t =>
      `<option value="${t.template_id}">${t.name}</option>`
    ).join('');

  } catch (error) {
    console.error('Error loading template dropdown:', error);

    // Fallback to defaults
    const defaults = getDefaultTemplates();
    select.innerHTML = defaults.map(t =>
      `<option value="${t.template_id}">${t.name}</option>`
    ).join('');
  }
}

function openTemplateModal(templateId = null) {
  editingTemplateId = templateId;
  const modal = document.getElementById('template-modal');
  const title = document.getElementById('template-modal-title');
  const nameInput = document.getElementById('template-name');
  const descInput = document.getElementById('template-description');
  const exampleInput = document.getElementById('template-example');

  if(templateId) {
    title.textContent = 'Edit Template';
    const template = templatesCache.find(t => t.template_id === templateId);
    if(template) {
      nameInput.value = template.name || '';
      descInput.value = template.description || '';
      exampleInput.value = template.example_output || '';
    }
  } else {
    title.textContent = 'New Template';
    nameInput.value = '';
    descInput.value = '';
    exampleInput.value = '';
  }

  modal.classList.remove('hidden');
}

function closeTemplateModal() {
  const modal = document.getElementById('template-modal');
  modal.classList.add('hidden');
  editingTemplateId = null;
}

async function saveTemplate() {
  const nameInput = document.getElementById('template-name');
  const descInput = document.getElementById('template-description');
  const exampleInput = document.getElementById('template-example');

  const name = nameInput.value.trim();
  const description = descInput.value.trim();
  const example_output = exampleInput.value.trim();

  if(!name) {
    alert('Please enter a template name');
    return;
  }

  if(!example_output) {
    alert('Please provide an example note');
    return;
  }

  try {
    const method = editingTemplateId ? 'PUT' : 'POST';
    const url = editingTemplateId
      ? `${MAIN_API}/templates/${editingTemplateId}`
      : `${MAIN_API}/templates`;

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': idToken
      },
      body: JSON.stringify({ name, description, example_output })
    });

    if(!response.ok) throw new Error('Failed to save template');

    closeTemplateModal();
    loadTemplates();
    loadTemplateDropdown();

  } catch (error) {
    console.error('Error saving template:', error);
    alert('Failed to save template: ' + error.message);
  }
}

async function deleteTemplate(templateId) {
  if(!confirm('Are you sure you want to delete this template?')) return;

  try {
    const response = await fetch(`${MAIN_API}/templates/${templateId}`, {
      method: 'DELETE',
      headers: { 'Authorization': idToken}
    });

    if(!response.ok) throw new Error('Failed to delete template');

    loadTemplates();
    loadTemplateDropdown();

  } catch (error) {
    console.error('Error deleting template:', error);
    alert('Failed to delete template: ' + error.message);
  }
}

// Make functions globally available for onclick handlers
window.editTemplate = (id) => openTemplateModal(id);
window.deleteTemplate = deleteTemplate;

// ============================================
// Visits Functions
// ============================================
async function loadVisits() {
  console.log("📡 loadVisits called. Token exists?", !!idToken); // DEBUG

  const list = document.getElementById('visits-list');
  if(!list) return;

  list.innerHTML = `
    <div class="loading-spinner">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading visits...</span>
    </div>
  `;

  try {
    // Admin gets all visits, users get their own
    const url = userRole === 'admin'
      ? `${MAIN_API}/notes?all=true`
      : `${MAIN_API}/notes`;

    const response = await fetch(url, {
      headers: { 'Authorization': idToken }
    });

    if (!response.ok) throw new Error('Failed to load visits');

    const data = await response.json();
    visitsCache = data.notes || [];

    renderVisits();
  } catch (error) {
    console.error('Error loading visits:', error);
    list.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-exclamation-circle"></i>
        <p>Failed to load visits. Please try again.</p>
      </div>
    `;
  }
}

function renderVisits(filter = 'all', searchQuery = '') {
  const list = document.getElementById('visits-list');
  if(!list) return;

  let filtered = [...visitsCache];

  // Apply search filter
  if(searchQuery) {
    const query = searchQuery.toLowerCase();
    filtered = filtered.filter(v =>
      (v.patient_name || '').toLowerCase().includes(query)
    );
  }

  // Apply time filter
  const now = new Date();
  if(filter === 'today') {
    filtered = filtered.filter(v => {
      const date = new Date(v.timestamp);
      return date.toDateString() === now.toDateString();
    });
  } else if(filter === 'week') {
    const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
    filtered = filtered.filter(v => new Date(v.timestamp) >= weekAgo);
  } else if(filter === 'month') {
    const monthAgo = new Date(now - 30 * 24 * 60 * 60 * 1000);
    filtered = filtered.filter(v => new Date(v.timestamp) >= monthAgo);
  }

  if(filtered.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-clipboard"></i>
        <p>No visits found</p>
      </div>
    `;
    return;
  }

  list.innerHTML = filtered.map(visit => {
    const date = new Date(visit.timestamp);
    const formattedDate = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
    const formattedTime = date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit'
    });

    return `
      <div class="visit-card" data-id="${visit.user_id}#${visit.timestamp}">
        <div class="visit-icon">
          <i class="fa-solid fa-notes-medical"></i>
        </div>
        <div class="visit-info">
          <div class="visit-patient">${visit.patient_name || 'Unknown Patient'}</div>
          <div class="visit-meta">
            <span><i class="fa-regular fa-calendar"></i> ${formattedDate}</span>
            <span><i class="fa-regular fa-clock"></i> ${formattedTime}</span>
            ${userRole === 'admin' && visit.provider_email ? `
              <span><i class="fa-regular fa-user"></i> ${visit.provider_email}</span>
            ` : ''}
          </div>
        </div>
        <div class="visit-actions">
          <button class="btn-view" onclick="viewVisit('${visit.user_id}', '${visit.timestamp}')">
            View
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function viewVisit(userId, timestamp) {
  const visit = visitsCache.find(v =>
    v.user_id === userId && v.timestamp === timestamp
  );

  if(!visit) return;

  const modal = document.getElementById('visit-modal');
  const title = document.getElementById('visit-modal-title');
  const transcript = document.getElementById('visit-transcript');
  const note = document.getElementById('visit-note');

  title.textContent = visit.patient_name || 'Visit Details';
  transcript.textContent = visit.transcript || 'No transcript available';
  note.textContent = visit.soap_note || 'No note available';

  modal.classList.remove('hidden');
}

window.viewVisit = viewVisit;

function closeVisitModal() {
  const modal = document.getElementById('visit-modal');
  modal.classList.add('hidden');
}

// ============================================
// Settings Functions
// ============================================
function loadSettings() {
  updateUserDisplay();
}

// ============================================
// Invite Team Functions
// ============================================
async function sendInvite() {
  const emailInput = document.getElementById('invite-email');
  const nameInput = document.getElementById('invite-name');
  const roleSelect = document.getElementById('invite-role');

  const email = emailInput?.value.trim();
  const name = nameInput?.value.trim();
  const role = roleSelect?.value || 'user';

  if (!email) {
    showError('invite-error', 'Please enter an email address');
    return;
  }

  if (!name) {
    showError('invite-error', 'Please enter a name');
    return;
  }

  // Email validation
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    showError('invite-error', 'Please enter a valid email address');
    return;
  }

  try {
    const response = await fetch(`${MAIN_API}/admin/invite`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': idToken
      },
      body: JSON.stringify({ email, name, role })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to send invitation');
    }

    showSuccess('invite-success', `Invitation sent to ${email}!`);

    // Clear form
    emailInput.value = '';
    nameInput.value = '';
    roleSelect.value = 'user';

    // Refresh team list
    loadTeamMembers();

  } catch (error) {
    console.error('Invite error:', error);
    showError('invite-error', error.message);
  }
}

async function loadTeamMembers() {
  const list = document.getElementById('team-members-list');
  if (!list) return;

  list.innerHTML = `
    <div class="loading-spinner">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <span>Loading team...</span>
    </div>
  `;

  try {
    const response = await fetch(`${MAIN_API}/admin/users`, {
      headers: { 'Authorization':idToken }
    });

    if (!response.ok) throw new Error('Failed to load team');

    const data = await response.json();
    const users = data.users || [];

    if (users.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <i class="fa-solid fa-users"></i>
          <p>No team members yet</p>
        </div>
      `;
      return;
    }

    list.innerHTML = users.map(user => {
      const initials = (user.name || user.email || '??')
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .substring(0, 2);

      const status = user.status || 'active';
      const badgeClass = user.role === 'admin' ? 'admin' : (status === 'pending' ? 'pending' : 'user');
      const badgeText = status === 'pending' ? 'Pending' : (user.role === 'admin' ? 'Admin' : 'User');

      return `
        <div class="team-member-card">
          <div class="team-member-avatar">${initials}</div>
          <div class="team-member-info">
            <div class="team-member-name">${user.name || 'No Name'}</div>
            <div class="team-member-email">${user.email}</div>
          </div>
          <span class="team-member-badge ${badgeClass}">${badgeText}</span>
        </div>
      `;
    }).join('');

  } catch (error) {
    console.error('Error loading team:', error);
    list.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-exclamation-circle"></i>
        <p>Failed to load team members</p>
      </div>
    `;
  }
}

// ============================================
// Mic Test Modal Functions
// ============================================
async function openMicTestModal() {
  const modal = document.getElementById('mic-test-modal');
  const micSelect = document.getElementById('mic-select');

  modal.classList.remove('hidden');

  // Enumerate audio devices
  try {
    // Request permission first
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop());

    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter(d => d.kind === 'audioinput');

    micSelect.innerHTML = audioInputs.map((device, index) =>
      `<option value="${device.deviceId}">${device.label || `Microphone ${index + 1}`}</option>`
    ).join('');

    // Select previously chosen mic or default
    if (selectedMicId) {
      micSelect.value = selectedMicId;
    }

    // Start testing with selected mic
    startMicTest(micSelect.value);

  } catch (error) {
    console.error('Mic access error:', error);
    micSelect.innerHTML = '<option value="">Microphone access denied</option>';
    updateMicStatus(false, 'Please allow microphone access');
  }
}

function closeMicTestModal() {
  const modal = document.getElementById('mic-test-modal');
  modal.classList.add('hidden');
  stopMicTest();
}

async function startMicTest(deviceId) {
  // Stop any existing test
  stopMicTest();

  try {
    const constraints = {
      audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true
      }
    };

    micTestStream = await navigator.mediaDevices.getUserMedia(constraints);

    // Create audio context and analyser
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioContext.createMediaStreamSource(micTestStream);
    micAnalyser = audioContext.createAnalyser();
    micAnalyser.fftSize = 256;
    source.connect(micAnalyser);

    // Store selected mic
    selectedMicId = deviceId;

    // Start visualizing
    visualizeMicLevel();

    updateMicStatus(true, 'Microphone ready');

  } catch (error) {
    console.error('Mic test error:', error);
    updateMicStatus(false, 'Could not access microphone');
  }
}

function stopMicTest() {
  if (micAnimationFrame) {
    cancelAnimationFrame(micAnimationFrame);
    micAnimationFrame = null;
  }

  if (micTestStream) {
    micTestStream.getTracks().forEach(track => track.stop());
    micTestStream = null;
  }

  micAnalyser = null;

  // Reset level bar
  const fill = document.getElementById('mic-level-fill');
  const value = document.getElementById('mic-level-value');
  if (fill) fill.style.width = '0%';
  if (value) value.textContent = '0%';
}

function visualizeMicLevel() {
  if (!micAnalyser) return;

  const dataArray = new Uint8Array(micAnalyser.frequencyBinCount);

  function update() {
    if (!micAnalyser) return;

    micAnalyser.getByteFrequencyData(dataArray);

    // Calculate average volume
    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    const percentage = Math.min(100, Math.round((average / 128) * 100));

    // Update UI
    const fill = document.getElementById('mic-level-fill');
    const value = document.getElementById('mic-level-value');

    if (fill) fill.style.width = `${percentage}%`;
    if (value) value.textContent = `${percentage}%`;

    micAnimationFrame = requestAnimationFrame(update);
  }

  update();
}

function updateMicStatus(isGood, message) {
  const status = document.getElementById('mic-status');
  if (!status) return;

  if (isGood) {
    status.className = 'mic-status';
    status.innerHTML = `<i class="fa-solid fa-circle-check"></i><span>${message}</span>`;
  } else {
    status.className = 'mic-status error';
    status.innerHTML = `<i class="fa-solid fa-circle-xmark"></i><span>${message}</span>`;
  }
}

// ============================================
// Quick Mic Check on Login
// ============================================
async function showQuickMicCheck() {
  const popup = document.getElementById('mic-check-popup');
  const deviceLabel = document.getElementById('mic-check-device');
  const bar = document.getElementById('mic-check-bar');

  if (!popup) return;

  try {
    // Get mic access
    quickMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });

    // Get device name
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter(d => d.kind === 'audioinput');
    const activeTrack = quickMicStream.getAudioTracks()[0];
    const activeDevice = audioInputs.find(d => d.deviceId === activeTrack.getSettings().deviceId);

    // Store the selected mic for later use
    if (activeTrack.getSettings().deviceId) {
      selectedMicId = activeTrack.getSettings().deviceId;
    }

    if (deviceLabel) {
      deviceLabel.textContent = activeDevice?.label || 'Default Microphone';
    }

    // Set up audio analysis
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioContext.createMediaStreamSource(quickMicStream);
    quickMicAnalyser = audioContext.createAnalyser();
    quickMicAnalyser.fftSize = 256;
    source.connect(quickMicAnalyser);

    // Show popup
    popup.classList.remove('hidden');

    // Animate level bar
    const dataArray = new Uint8Array(quickMicAnalyser.frequencyBinCount);
    function updateLevel() {
      if (!quickMicAnalyser) return;
      quickMicAnalyser.getByteFrequencyData(dataArray);
      const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
      const pct = Math.min(100, Math.round((avg / 128) * 100));
      if (bar) bar.style.width = `${pct}%`;
      quickMicAnimation = requestAnimationFrame(updateLevel);
    }
    updateLevel();

    // Auto-close after 5 seconds
    setTimeout(() => closeQuickMicCheck(), 5000);

  } catch (error) {
    console.log('Mic check skipped:', error.message);
  }
}

function closeQuickMicCheck() {
  const popup = document.getElementById('mic-check-popup');
  if (popup) popup.classList.add('hidden');

  if (quickMicAnimation) {
    cancelAnimationFrame(quickMicAnimation);
    quickMicAnimation = null;
  }

  if (quickMicStream) {
    quickMicStream.getTracks().forEach(track => track.stop());
    quickMicStream = null;
  }

  quickMicAnalyser = null;
}

// ============================================
// Patient Management Functions
// ============================================
async function searchPatients(query) {
  if (!query || query.length < 1) return [];

  console.log("🔍 Searching patients:", query); // DEBUG

  try {
    const response = await fetch(
      `${PATIENTS_API}/patients/search?q=${encodeURIComponent(query)}`,
      { headers: { 'Authorization': idToken } }
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

  if (!query || query.length < 1) {
    resultsDiv.style.display = 'none';
    return;
  }

  const patients = await searchPatients(query);
  resultsDiv.innerHTML = '';
  resultsDiv.style.display = 'block';

  if (patients.length > 0) {
    patients.forEach(patient => {
      const item = document.createElement('div');
      item.className = 'patient-result-item';
      item.innerHTML = `<strong>${patient.name}</strong> <span style="color:#64748b; font-size:0.8em">${patient.patient_id ? '#' + patient.patient_id.substring(4,8) : ''}</span>`;
      item.onclick = () => selectPatient(patient);
      resultsDiv.appendChild(item);
    });
  }

  // Always show "Create new" option
  const addNew = document.createElement('div');
  addNew.className = 'patient-result-item add-new';
  addNew.innerHTML = `<i class="fa-solid fa-plus"></i> Create new: "${query}"`;
  addNew.onclick = () => createNewPatient(query);
  resultsDiv.appendChild(addNew);
}

async function createNewPatient(name) {
  // --- TRUTH SERUM DEBUG START ---
  console.log("⚠️ ATTEMPTING API CALL: createNewPatient ⚠️");
  console.log("1. Endpoint:", `${PATIENTS_API}/patients`);
  console.log("2. Token value:", idToken);
  console.log("3. Token Type:", typeof idToken);

  const headersToSend = {
    'Content-Type': 'application/json',
    'Authorization': idToken
  };
  console.log("4. HEADERS BEING SENT:", headersToSend);
  // --- TRUTH SERUM DEBUG END ---

  try {
    const response = await fetch(`${PATIENTS_API}/patients`, {
      method: 'POST',
      headers: headersToSend, // Using the debugged headers variable
      body: JSON.stringify({ name: name.trim() })
    });

    if (!response.ok) {
        console.error("❌ API ERROR RESPONSE:", response.status, response.statusText);
        throw new Error('Failed to create patient');
    }

    const data = await response.json();
    selectPatient(data.patient);
  } catch (error) {
    console.error("❌ CATCH BLOCK ERROR:", error);
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

  // --- FIX: Clear previous results when starting new recording ---
  const transcriptEl = document.getElementById('transcript');
  const soapEl = document.getElementById('soap-note');
  if(transcriptEl) transcriptEl.value = '';
  if(soapEl) soapEl.value = '';
  // -------------------------------------------------------------

  try {
     const constraints = {
      audio: {
        deviceId: selectedMicId ? { exact: selectedMicId } : undefined,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000
      }
    };

    const stream = await navigator.mediaDevices.getUserMedia(constraints);

    const options = { mimeType: 'audio/webm;codecs=opus', bitsPerSecond: 16000 };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      delete options.mimeType;
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

    const recordBtn = document.getElementById('record-btn');
    const status = document.getElementById('recording-status');
    const resultsPanel = document.getElementById('results-panel');

    if(recordBtn) {
      recordBtn.classList.add('recording');
      recordBtn.innerHTML = '<i class="fa-solid fa-stop"></i>';
    }

    if(status) status.textContent = 'Recording in progress...';

    if(resultsPanel) {
      resultsPanel.classList.remove('hidden');
      resultsPanel.classList.add('takeover');
    }

    // Show mobile results toolbar
    const resultsToolbar = document.getElementById('results-toolbar');
    if(resultsToolbar) {
      resultsToolbar.classList.remove('hidden');
      resultsToolbar.classList.add('visible');
    }

    // Hide setup panel during recording/results
    const setupPanel = document.getElementById('setup-panel');
    if(setupPanel) setupPanel.classList.add('hidden');

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
      recordBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
    }

    if(status) status.textContent = 'Processing audio...';

    // Keep results view visible for reviewing
    const resultsToolbar = document.getElementById('results-toolbar');
    if(resultsToolbar) resultsToolbar.classList.add('visible');
  }
}

// ============================================
// AI Processing
// ============================================

// Global loader helpers for seamless UX during transcription and note generation
function showLoader(text = 'Processing...') {
  const overlay = document.getElementById('global-loader');
  const textEl = document.getElementById('loader-text');
  if (textEl && typeof text === 'string') textEl.textContent = text;
  if (overlay) overlay.classList.remove('hidden');
  // Disable key interactive controls to prevent duplicate actions
  const recordBtn = document.getElementById('record-btn');
  if (recordBtn) recordBtn.disabled = true;
  const uploadLabel = document.getElementById('upload-audio-label');
  if (uploadLabel) { uploadLabel.style.pointerEvents = 'none'; uploadLabel.style.opacity = '0.6'; }
}
function setLoaderText(text) {
  const textEl = document.getElementById('loader-text');
  if (textEl && typeof text === 'string') textEl.textContent = text;
}
function hideLoader() {
  const overlay = document.getElementById('global-loader');
  if (overlay) overlay.classList.add('hidden');
  const recordBtn = document.getElementById('record-btn');
  if (recordBtn) recordBtn.disabled = false;
  const uploadLabel = document.getElementById('upload-audio-label');
  if (uploadLabel) { uploadLabel.style.pointerEvents = ''; uploadLabel.style.opacity = ''; }
}
async function transcribeAudio(audioBlob) {
  try {
    showLoader('Transcribing audio...');
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);
    await new Promise(resolve => reader.onloadend = resolve);
    const base64Audio = reader.result.split(',')[1];

    const response = await fetch(`${MAIN_API}/transcribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': idToken
      },
      body: JSON.stringify({ audio: base64Audio })
    });

    if (!response.ok) throw new Error('Transcription failed');

    const data = await response.json();
    const transcript = data.transcript;

    // --- FIX: Check for empty transcript ---
    if (!transcript || transcript.trim().length === 0) {
      console.warn("Empty transcript received");

      const status = document.getElementById('recording-status');
      if(status) {
        status.textContent = 'No Transcript Detected';
        status.style.color = '#ef4444'; // Red text
        // Reset color after 3 seconds
        setTimeout(() => {
            status.textContent = 'Ready to record';
            status.style.color = '';
        }, 3000);
      }
      hideLoader();
      return; // STOP HERE! Do not generate note.
    }
    // ---------------------------------------

    const transcriptEl = document.getElementById('transcript');
    if(transcriptEl) transcriptEl.value = transcript;

    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Generating Clinical Note...';
    setLoaderText('Generating clinical note...');

    await generateVisitSummary(transcript);

  } catch (error) {
    alert('Error: ' + error.message);
    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Error processing audio';
  } finally {
    hideLoader();
  }
}

async function generateVisitSummary(transcript) {
  try {
    const templateSelect = document.getElementById('template-select');
    const template = templateSelect ? templateSelect.value : 'default_soap';

    const response = await fetch(`${MAIN_API}/generate-note`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': idToken
      },
      body: JSON.stringify({
        transcript: transcript,
        patient_name: selectedPatient ? selectedPatient.name : 'Unknown',
        patient_id: selectedPatient ? selectedPatient.patient_id : null,
        template_id: template
      })
    });

    if (!response.ok) throw new Error('Generation failed');
    const data = await response.json();

    const soapEl = document.getElementById('soap-note');
    if(soapEl) soapEl.value = data.note;

    const status = document.getElementById('recording-status');
    if(status) status.textContent = 'Note Generated Successfully';

  } catch (error) {
    const soapEl = document.getElementById('soap-note');
    if(soapEl) soapEl.value = 'Failed to generate note.';
  }
}

// ============================================
// Initialization & Listeners
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  console.log("🚀 Scribe32 App Loaded");
  // --- FIX: Clear stale data on page load ---
  const transcriptEl = document.getElementById('transcript');
  const soapEl = document.getElementById('soap-note');
  const statusEl = document.getElementById('recording-status');

  if(transcriptEl) transcriptEl.value = '';
  if(soapEl) soapEl.value = '';
  if(statusEl) statusEl.textContent = 'Ready to record';

  // ============================================
  // Login Handlers
  // ============================================
  function handleLoginSubmit() {
    const emailInput = document.getElementById('email');
    const passInput = document.getElementById('password');

    if (!emailInput || !passInput) return;

    const email = emailInput.value.trim();
    const password = passInput.value;

    if (email && password) {
      login(email, password);
    } else {
      alert('Please enter both email and password');
    }
  }

  const loginBtn = document.getElementById('login-btn');
  if (loginBtn) {
    loginBtn.addEventListener('click', (e) => {
      e.preventDefault();
      handleLoginSubmit();
    });
  }

  // Login Enter Key Support
  ['email', 'password'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleLoginSubmit();
        }
      });
    }
  });

  // Logout
  const logoutBtn = document.getElementById('logout-btn');
  if(logoutBtn) logoutBtn.addEventListener('click', logout);

  // ============================================
  // Forgot Password Handlers
  // ============================================
  const forgotPasswordLink = document.getElementById('forgot-password-link');
  if (forgotPasswordLink) {
    forgotPasswordLink.addEventListener('click', (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('email');
      const forgotEmailInput = document.getElementById('forgot-email');
      if (emailInput && forgotEmailInput && emailInput.value) {
        forgotEmailInput.value = emailInput.value;
      }
      showScreen('forgot-password-screen');
    });
  }

  const sendCodeBtn = document.getElementById('send-code-btn');
  if (sendCodeBtn) {
    sendCodeBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const forgotEmailInput = document.getElementById('forgot-email');
      if (forgotEmailInput) {
        initiateForgotPassword(forgotEmailInput.value);
      }
    });
  }

  const resetPasswordBtn = document.getElementById('reset-password-btn');
  if (resetPasswordBtn) {
    resetPasswordBtn.addEventListener('click', (e) => {
      e.preventDefault();
      confirmNewPassword(
        document.getElementById('verification-code')?.value,
        document.getElementById('new-password')?.value,
        document.getElementById('confirm-password')?.value
      );
    });
  }

  // Back to Login Links
  ['back-to-login-1', 'back-to-login-2'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        resetEmail = null;
        showScreen('login-screen');
      });
    }
  });

  // ============================================
  // Navigation (sidebar + bottom nav)
  // ============================================
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const view = item.dataset.view;
      if(view) {
        showView(view);
      }
    });
  });

  // Mobile bottom nav logout/profile
  const logoutMobile = document.getElementById('logout-btn-mobile');
  if (logoutMobile) logoutMobile.addEventListener('click', logout);

  // Sidebar Toggle
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');
  if(sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
    });
  }

  // ============================================
  // Patient Search
  // ============================================
  const patientSearch = document.getElementById('patient-search');
  let searchTimeout;
  if(patientSearch) {
    patientSearch.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => showPatientResults(e.target.value), 300);
    });

    document.addEventListener('click', (e) => {
      const results = document.getElementById('patient-results');
      if (results && !e.target.closest('.card-row')) {
        results.style.display = 'none';
      }
    });
  }

  // ============================================
  // Recording
  // ============================================
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

  // Back to setup
  const backBtn = document.getElementById('back-to-setup');
  if(backBtn) {
    backBtn.addEventListener('click', () => {
      const resultsPanel = document.getElementById('results-panel');
      const resultsToolbar = document.getElementById('results-toolbar');
      const setupPanel = document.getElementById('setup-panel');
      if(resultsPanel) {
        resultsPanel.classList.add('hidden');
        resultsPanel.classList.remove('takeover');
      }
      if(resultsToolbar) {
        resultsToolbar.classList.add('hidden');
        resultsToolbar.classList.remove('visible');
      }
      if(setupPanel) setupPanel.classList.remove('hidden');
    });
  }

  // Copy Buttons (desktop header + mobile toolbar)
  function handleCopy(btn) {
    const note = document.getElementById('soap-note');
    if(note) {
      const text = note.value ?? note.innerText;
      navigator.clipboard.writeText(text || '');
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = btn.id === 'copy-btn' ? 'Copy' : 'Copy';
        btn.classList.remove('copied');
      }, 1500);
    }
  }
  const copyBtn = document.getElementById('copy-btn');
  if(copyBtn) copyBtn.addEventListener('click', () => handleCopy(copyBtn));
  const copyBtnMobile = document.getElementById('copy-btn-mobile');
  if(copyBtnMobile) copyBtnMobile.addEventListener('click', () => handleCopy(copyBtnMobile));

  // ============================================
  // Templates Modal
  // ============================================
  const addTemplateBtn = document.getElementById('add-template-btn');
  if(addTemplateBtn) {
    addTemplateBtn.addEventListener('click', () => openTemplateModal());
  }

  const closeTemplateModalBtn = document.getElementById('close-template-modal');
  if(closeTemplateModalBtn) {
    closeTemplateModalBtn.addEventListener('click', closeTemplateModal);
  }

  const cancelTemplateBtn = document.getElementById('cancel-template-btn');
  if(cancelTemplateBtn) {
    cancelTemplateBtn.addEventListener('click', closeTemplateModal);
  }

  const saveTemplateBtn = document.getElementById('save-template-btn');
  if(saveTemplateBtn) {
    saveTemplateBtn.addEventListener('click', saveTemplate);
  }

  // ============================================
  // Visits Modal
  // ============================================
  const closeVisitModalBtn = document.getElementById('close-visit-modal');
  if(closeVisitModalBtn) {
    closeVisitModalBtn.addEventListener('click', closeVisitModal);
  }

  // Visits Filters
  const visitsSearch = document.getElementById('visits-search');
  const visitsFilter = document.getElementById('visits-filter');

  if(visitsSearch) {
    visitsSearch.addEventListener('input', (e) => {
      renderVisits(visitsFilter?.value || 'all', e.target.value);
    });
  }

  if(visitsFilter) {
    visitsFilter.addEventListener('change', (e) => {
      renderVisits(e.target.value, visitsSearch?.value || '');
    });
  }

  // ============================================
  // Settings - Change Password
  // ============================================
  const changePasswordBtn = document.getElementById('change-password-btn');
  if(changePasswordBtn) {
    changePasswordBtn.addEventListener('click', () => {
      changePassword(
        document.getElementById('current-password')?.value,
        document.getElementById('settings-new-password')?.value,
        document.getElementById('settings-confirm-password')?.value
      );
    });
  }

  // Close modals on outside click
  document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if(e.target === modal) {
        modal.classList.add('hidden');
        // Stop mic test if closing mic modal
        if(modal.id === 'mic-test-modal') {
          stopMicTest();
        }
      }
    });
  });

  // ============================================
  // Invite Team
  // ============================================
  const sendInviteBtn = document.getElementById('send-invite-btn');
  if(sendInviteBtn) {
    sendInviteBtn.addEventListener('click', sendInvite);
  }

  // ============================================
  // Mic Test Modal
  // ============================================
  const testMicBtn = document.getElementById('test-mic-btn');
  if(testMicBtn) {
    testMicBtn.addEventListener('click', openMicTestModal);
  }

  const closeMicModalBtn = document.getElementById('close-mic-modal');
  if(closeMicModalBtn) {
    closeMicModalBtn.addEventListener('click', closeMicTestModal);
  }

  const micTestDoneBtn = document.getElementById('mic-test-done-btn');
  if(micTestDoneBtn) {
    micTestDoneBtn.addEventListener('click', closeMicTestModal);
  }

  const micSelect = document.getElementById('mic-select');
  if(micSelect) {
    micSelect.addEventListener('change', (e) => {
      startMicTest(e.target.value);
    });
  }

  // ============================================
  // Upload Audio handler
  // ============================================
  const uploadInput = document.getElementById('upload-audio');
  if (uploadInput) {
    uploadInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      if (!selectedPatient) {
        alert('Please select or create a patient first');
        uploadInput.value = '';
        return;
      }

      try {
        const status = document.getElementById('recording-status');
        if (status) status.textContent = 'Uploading audio...';

        const arrayBuffer = await file.arrayBuffer();
        const blob = new Blob([arrayBuffer], { type: file.type || 'audio/webm' });

        // Reveal results panel like after recording
        const resultsPanel = document.getElementById('results-panel');
        const setupPanel = document.getElementById('setup-panel');
        const resultsToolbar = document.getElementById('results-toolbar');
        if (resultsPanel) { resultsPanel.classList.remove('hidden'); resultsPanel.classList.add('takeover'); }
        if (setupPanel) setupPanel.classList.add('hidden');
        if (resultsToolbar) { resultsToolbar.classList.remove('hidden'); resultsToolbar.classList.add('visible'); }

        await transcribeAudio(blob);
      } catch (err) {
        console.error('Upload error', err);
        alert('Failed to process uploaded audio');
      } finally {
        uploadInput.value = '';
      }
    });
  }

  // ============================================
  // Quick Mic Check Popup
  // ============================================
  const micCheckClose = document.getElementById('mic-check-close');
  if(micCheckClose) {
    micCheckClose.addEventListener('click', closeQuickMicCheck);
  }
});