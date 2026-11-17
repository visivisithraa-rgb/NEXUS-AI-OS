const { contextBridge, ipcRenderer } = require('electron');

// Expose safe, isolated APIs to the frontend
contextBridge.exposeInMainWorld('nexusDesktop', {
    isElectron: true,
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    getVersion: () => ipcRenderer.invoke('get-app-version'),
    getDataDir: () => ipcRenderer.invoke('get-data-dir')
});
