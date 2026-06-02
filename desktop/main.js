"use strict";

const { app, BrowserWindow, globalShortcut, ipcMain, Menu, shell } = require("electron");
const path = require("node:path");

const CLIENT_ENTRY = path.join(__dirname, "..", "app", "web", "index.html");
const configuredApiEndpoints = (process.env.MEKAMB_MUSIC_URLS || process.env.MEKAMB_MUSIC_URL || "")
  .split(/[,\n]/)
  .map((url) => url.trim())
  .filter(Boolean);

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 920,
    minHeight: 620,
    title: "Mekamb Music",
    backgroundColor: "#050607",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.loadFile(CLIENT_ENTRY);
}

function sendMediaCommand(command) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("desktop-media-command", command);
}

function registerMediaShortcuts() {
  const shortcuts = new Map([
    ["MediaPlayPause", "play-pause"],
    ["MediaNextTrack", "next"],
    ["MediaPreviousTrack", "previous"],
    ["MediaStop", "stop"],
  ]);

  for (const [accelerator, command] of shortcuts) {
    globalShortcut.register(accelerator, () => {
      sendMediaCommand(command);
    });
  }
}

function createMenu() {
  const template = [
    {
      label: "Mekamb Music",
      submenu: [
        {
          label: "Otwórz bibliotekę",
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.loadFile(CLIENT_ENTRY);
            }
          },
        },
        {
          label: "Odśwież",
          accelerator: "CmdOrCtrl+R",
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.reload();
            }
          },
        },
        { type: "separator" },
        { role: "quit", label: "Zamknij" },
      ],
    },
    {
      label: "Odtwarzanie",
      submenu: [
        {
          label: "Play / Pause",
          click: () => sendMediaCommand("play-pause"),
        },
        {
          label: "Poprzedni",
          accelerator: "Alt+Left",
          click: () => sendMediaCommand("previous"),
        },
        {
          label: "Następny",
          accelerator: "Alt+Right",
          click: () => sendMediaCommand("next"),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  createMenu();
  createWindow();
  registerMediaShortcuts();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

ipcMain.handle("desktop-api-endpoints", () => configuredApiEndpoints);

ipcMain.handle("desktop-fetch", async (_event, request) => {
  const url = new URL(request.url);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("Desktop API requests require http or https URLs.");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), request.timeoutMs || 20000);

  try {
    const response = await fetch(url, {
      method: request.method || "GET",
      headers: request.headers || {},
      body: request.body,
      signal: controller.signal,
    });
    const body = response.status === 204 ? null : await response.arrayBuffer();

    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries()),
      body,
    };
  } finally {
    clearTimeout(timeout);
  }
});
