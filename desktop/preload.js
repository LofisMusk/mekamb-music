"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("mekambDesktop", {
  isDesktop: true,
  fetchApi(request) {
    return ipcRenderer.invoke("desktop-fetch", request);
  },
  getConfiguredApiEndpoints() {
    return ipcRenderer.invoke("desktop-api-endpoints");
  },
  onMediaCommand(callback) {
    if (typeof callback !== "function") return () => {};

    const listener = (_event, command) => {
      callback(command);
    };
    ipcRenderer.on("desktop-media-command", listener);

    return () => {
      ipcRenderer.removeListener("desktop-media-command", listener);
    };
  },
});
