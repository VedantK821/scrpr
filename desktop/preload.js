// Minimal preload — security isolation
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('scrpr', {
  platform: process.platform,
  isDesktop: true,
});
