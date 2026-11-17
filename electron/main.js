const { app, BrowserWindow, ipcMain, dialog, session } = require('electron');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow = null;
let splashWindow = null;
let backendProcess = null;
const BACKEND_PORT = process.env.PORT || 5000;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const isDev = !app.isPackaged;

// Persistent User Data Directory
const userDataDir = app.getPath('userData');
if (!fs.existsSync(userDataDir)) {
    fs.mkdirSync(userDataDir, { recursive: true });
}

// ---------------------------------------------------------------------------
// 1. SPLASH SCREEN (Startup loading window)
// ---------------------------------------------------------------------------
function createSplashWindow() {
    splashWindow = new BrowserWindow({
        width: 480,
        height: 320,
        frame: false,
        resizable: false,
        alwaysOnTop: true,
        transparent: true,
        center: true,
        icon: path.join(__dirname, '..', 'build', 'icon.ico'),
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    splashWindow.loadFile(path.join(__dirname, 'splash.html'));
}

// ---------------------------------------------------------------------------
// 2. MAIN APPLICATION WINDOW
// ---------------------------------------------------------------------------
function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 820,
        minWidth: 980,
        minHeight: 640,
        title: "NEXUS AI OS",
        icon: path.join(__dirname, '..', 'build', 'icon.ico'),
        backgroundColor: '#100d20',
        show: false, // Show once ready
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
            preload: path.join(__dirname, 'preload.js')
        }
    });

    // Remove default menu bar for clean OS desktop feel
    mainWindow.setMenuBarVisibility(false);

    // Load frontend from local Flask backend server
    mainWindow.loadURL(BACKEND_URL);

    mainWindow.once('ready-to-show', () => {
        if (splashWindow && !splashWindow.isDestroyed()) {
            splashWindow.close();
            splashWindow = null;
        }
        mainWindow.show();
        mainWindow.focus();
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// ---------------------------------------------------------------------------
// 3. FLASK BACKEND LIFECYCLE MANAGEMENT
// ---------------------------------------------------------------------------
function findPythonBackend() {
    if (isDev) {
        // In development, prioritize local virtual environment
        const rootDir = path.join(__dirname, '..');
        const venvPython = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
        if (fs.existsSync(venvPython)) {
            return {
                command: venvPython,
                args: ['-u', path.join(rootDir, 'app.py')],
                cwd: rootDir
            };
        }
        return {
            command: 'python',
            args: ['-u', path.join(rootDir, 'app.py')],
            cwd: rootDir
        };
    } else {
        // In production packaged build
        const resourcesDir = process.resourcesPath;
        const exePath = path.join(resourcesDir, 'backend', 'nexus_backend.exe');
        if (fs.existsSync(exePath)) {
            return {
                command: exePath,
                args: [],
                cwd: path.join(resourcesDir, 'backend')
            };
        }
        // Fallback to app.exe if named app
        const altExePath = path.join(resourcesDir, 'backend', 'app.exe');
        if (fs.existsSync(altExePath)) {
            return {
                command: altExePath,
                args: [],
                cwd: path.join(resourcesDir, 'backend')
            };
        }
        throw new Error(`Packaged Python backend executable not found in ${resourcesDir}/backend`);
    }
}

function startBackend() {
    return new Promise((resolve, reject) => {
        try {
            const backendConfig = findPythonBackend();
            console.log(`[Electron] Starting Backend: ${backendConfig.command} with args:`, backendConfig.args);

            const env = {
                ...process.env,
                PORT: String(BACKEND_PORT),
                NEXUS_DATA_DIR: userDataDir,
                PYTHONUNBUFFERED: '1',
                FLASK_ENV: isDev ? 'development' : 'production'
            };

            backendProcess = spawn(backendConfig.command, backendConfig.args, {
                cwd: backendConfig.cwd,
                env: env,
                stdio: ['ignore', 'pipe', 'pipe']
            });

            backendProcess.stdout.on('data', (data) => {
                const text = data.toString();
                console.log(`[Backend STDOUT] ${text.trim()}`);
            });

            backendProcess.stderr.on('data', (data) => {
                const text = data.toString();
                console.log(`[Backend STDERR] ${text.trim()}`);
            });

            backendProcess.on('error', (err) => {
                console.error('[Electron] Failed to spawn backend process:', err);
                reject(err);
            });

            backendProcess.on('exit', (code, signal) => {
                console.log(`[Electron] Backend process exited with code ${code}, signal ${signal}`);
                backendProcess = null;
            });

            resolve();
        } catch (err) {
            reject(err);
        }
    });
}

function checkBackendHealth(maxAttempts = 45, intervalMs = 600) {
    return new Promise((resolve, reject) => {
        let attempts = 0;

        const check = () => {
            attempts++;
            const req = http.get(`${BACKEND_URL}/api/status`, (res) => {
                if (res.statusCode === 200) {
                    console.log(`[Electron] Backend health check passed after ${attempts} attempt(s)!`);
                    resolve(true);
                } else {
                    retry();
                }
            });

            req.on('error', () => {
                retry();
            });

            req.setTimeout(500, () => {
                req.destroy();
                retry();
            });
        };

        const retry = () => {
            if (attempts >= maxAttempts) {
                reject(new Error(`Backend failed to respond at ${BACKEND_URL} after ${maxAttempts} attempts.`));
            } else {
                setTimeout(check, intervalMs);
            }
        };

        check();
    });
}

function stopBackend() {
    return new Promise((resolve) => {
        if (!backendProcess) {
            resolve();
            return;
        }

        console.log('[Electron] Requesting graceful backend shutdown via /api/shutdown...');
        const req = http.request(`${BACKEND_URL}/api/shutdown`, { method: 'POST', timeout: 1500 }, () => {
            console.log('[Electron] Backend shutdown confirmed.');
            setTimeout(() => {
                if (backendProcess) {
                    try { backendProcess.kill(); } catch (e) {}
                }
                resolve();
            }, 300);
        });

        req.on('error', () => {
            console.log('[Electron] Direct kill fallback for backend process...');
            if (backendProcess) {
                try { backendProcess.kill('SIGTERM'); } catch (e) {}
            }
            resolve();
        });

        req.end();
    });
}

// ---------------------------------------------------------------------------
// 4. IPC CHANNELS (Desktop window controls & info)
// ---------------------------------------------------------------------------
ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    }
});

ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
});

ipcMain.handle('get-app-version', () => {
    return app.getVersion();
});

ipcMain.handle('get-data-dir', () => {
    return userDataDir;
});

// ---------------------------------------------------------------------------
// 5. APPLICATION INITIALIZATION & SHUTDOWN
// ---------------------------------------------------------------------------
app.whenReady().then(async () => {
    // Enable media (microphone) permissions for voice assistant
    if (session && session.defaultSession) {
        session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
            if (permission === 'media') {
                return callback(true);
            }
            callback(false);
        });

        session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
            if (permission === 'media') return true;
            return false;
        });
    }

    createSplashWindow();

    try {
        await startBackend();
        await checkBackendHealth();
        createMainWindow();
    } catch (err) {
        console.error('[Electron] Startup Failure:', err);
        if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
        dialog.showErrorBox(
            "NEXUS AI OS - Startup Error",
            `The background intelligence system could not be initialized.\n\nError: ${err.message}\n\nPlease verify that port ${BACKEND_PORT} is free and restart the application.`
        );
        app.quit();
    }

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createMainWindow();
        }
    });
});

app.on('before-quit', async (e) => {
    if (backendProcess) {
        e.preventDefault();
        await stopBackend();
        app.exit(0);
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
