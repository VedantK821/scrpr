const { app, BrowserWindow, Tray, Menu, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

let mainWindow = null;
let tray = null;
let backendProcess = null;
let frontendProcess = null;
let isQuitting = false;

// Determine if we're in development or packaged
const isDev = !app.isPackaged;
const resourcesPath = isDev ? path.join(__dirname, '..') : process.resourcesPath;

function log(msg) {
  console.log(`[Scrpr] ${msg}`);
}

// Wait for a server to be healthy
function waitForServer(url, maxRetries = 30, retryDelay = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      attempts++;
      http.get(url, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (attempts < maxRetries) {
          setTimeout(check, retryDelay);
        } else {
          reject(new Error(`Server at ${url} not healthy after ${maxRetries} attempts`));
        }
      }).on('error', () => {
        if (attempts < maxRetries) {
          setTimeout(check, retryDelay);
        } else {
          reject(new Error(`Server at ${url} not reachable after ${maxRetries} attempts`));
        }
      });
    };
    check();
  });
}

function startBackend() {
  const backendPath = isDev
    ? path.join(resourcesPath, 'backend')
    : path.join(resourcesPath, 'backend');
  const dbPath = path.join(app.getPath('userData'), 'scrpr.db');

  log(`Starting backend from: ${backendPath}`);
  log(`Database at: ${dbPath}`);

  const env = {
    ...process.env,
    DATABASE_URL: `sqlite+aiosqlite:///${dbPath}`,
    PYTHONUNBUFFERED: '1',
  };

  backendProcess = spawn(
    'python',
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: backendPath,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: true,
    }
  );

  backendProcess.stdout.on('data', (data) => log(`[Backend] ${data.toString().trim()}`));
  backendProcess.stderr.on('data', (data) => log(`[Backend] ${data.toString().trim()}`));
  backendProcess.on('error', (err) => log(`[Backend Error] ${err.message}`));
  backendProcess.on('close', (code) => {
    log(`[Backend] Process exited with code ${code}`);
    if (!isQuitting) {
      dialog.showErrorBox(
        'Scrpr Backend Error',
        'The backend server has stopped unexpectedly. The app will close.\n\nMake sure Python 3.12+ is installed with all dependencies.'
      );
      app.quit();
    }
  });

  return backendProcess;
}

function startFrontend() {
  const frontendPath = isDev
    ? path.join(resourcesPath, 'frontend')
    : path.join(resourcesPath, 'frontend');

  log(`Starting frontend from: ${frontendPath}`);

  const cmd = isDev ? 'npm' : 'npx';
  const args = isDev ? ['run', 'dev'] : ['next', 'start', '-p', '3000'];

  frontendProcess = spawn(cmd, args, {
    cwd: frontendPath,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: 'http://localhost:8000',
      PORT: '3000',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
  });

  frontendProcess.stdout.on('data', (data) => log(`[Frontend] ${data.toString().trim()}`));
  frontendProcess.stderr.on('data', (data) => log(`[Frontend] ${data.toString().trim()}`));
  frontendProcess.on('error', (err) => log(`[Frontend Error] ${err.message}`));
  frontendProcess.on('close', (code) => {
    log(`[Frontend] Process exited with code ${code}`);
  });

  return frontendProcess;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    title: 'Scrpr',
    backgroundColor: '#09090b',
    show: false, // Don't show until ready
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Show a loading state first
  mainWindow.loadURL(
    'data:text/html,' +
      encodeURIComponent(`
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          margin: 0;
          background: #09090b;
          color: #fafafa;
          font-family: 'Segoe UI', system-ui, sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100vh;
          flex-direction: column;
        }
        .brand {
          font-family: monospace;
          font-size: 28px;
          font-weight: bold;
          margin-bottom: 16px;
          letter-spacing: 2px;
        }
        .dot {
          display: inline-block;
          width: 10px;
          height: 10px;
          background: #06b6d4;
          border-radius: 50%;
          margin-right: 8px;
          box-shadow: 0 0 12px rgba(6, 182, 212, 0.5);
        }
        .status {
          color: #71717a;
          font-size: 14px;
        }
        .spinner {
          width: 20px;
          height: 20px;
          border: 2px solid #27272a;
          border-top-color: #06b6d4;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
          margin-bottom: 16px;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      </style>
    </head>
    <body>
      <div class="spinner"></div>
      <div class="brand"><span class="dot"></span>SCRPR</div>
      <div class="status">Starting services...</div>
    </body>
    </html>
  `)
  );

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  try {
    const iconPath = path.join(__dirname, 'icon.png');
    tray = new Tray(iconPath);
  } catch {
    // If no icon, skip tray on some platforms
    return;
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Scrpr',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Open in Browser',
      click: () => {
        require('electron').shell.openExternal('http://localhost:3000');
      },
    },
    {
      label: 'API Docs',
      click: () => {
        require('electron').shell.openExternal('http://localhost:8000/docs');
      },
    },
    { type: 'separator' },
    {
      label: 'Quit Scrpr',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Scrpr — AI Data Enrichment');
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

async function startApp() {
  createWindow();
  mainWindow.show();

  // Start servers
  log('Starting backend server...');
  startBackend();

  log('Starting frontend server...');
  startFrontend();

  // Wait for servers to be healthy
  try {
    log('Waiting for backend to be ready...');
    await waitForServer('http://localhost:8000/health', 30, 1000);
    log('Backend is ready!');

    log('Waiting for frontend to be ready...');
    await waitForServer('http://localhost:3000', 30, 1000);
    log('Frontend is ready!');

    // Load the app
    mainWindow.loadURL('http://localhost:3000');
    log('App loaded successfully!');
  } catch (err) {
    log(`Startup failed: ${err.message}`);
    dialog.showErrorBox(
      'Scrpr Startup Error',
      `Failed to start services:\n${err.message}\n\nMake sure Python 3.12+ and Node.js are installed.`
    );
    app.quit();
  }
}

// App lifecycle
app.whenReady().then(() => {
  createTray();
  startApp();
});

app.on('window-all-closed', () => {
  // On macOS, keep running in tray
  if (process.platform !== 'darwin') {
    isQuitting = true;
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    startApp();
  } else {
    mainWindow.show();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  log('Shutting down...');

  // Kill child processes
  if (backendProcess && !backendProcess.killed) {
    log('Stopping backend...');
    try {
      process.kill(backendProcess.pid, 'SIGTERM');
      // On Windows, also try taskkill
      if (process.platform === 'win32') {
        spawn('taskkill', ['/F', '/T', '/PID', String(backendProcess.pid)], { shell: true });
      }
    } catch (e) {
      log(`Error stopping backend: ${e.message}`);
    }
  }

  if (frontendProcess && !frontendProcess.killed) {
    log('Stopping frontend...');
    try {
      process.kill(frontendProcess.pid, 'SIGTERM');
      if (process.platform === 'win32') {
        spawn('taskkill', ['/F', '/T', '/PID', String(frontendProcess.pid)], { shell: true });
      }
    } catch (e) {
      log(`Error stopping frontend: ${e.message}`);
    }
  }
});
