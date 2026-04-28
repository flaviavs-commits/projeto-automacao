const fs = require("fs");
const path = require("path");

const express = require("express");
const QRCode = require("qrcode");
const pino = require("pino");
const { Boom } = require("@hapi/boom");
const {
  default: makeWASocket,
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} = require("baileys");

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  base: null,
});

const app = express();
app.use(express.json({ limit: "1mb" }));

const config = {
  apiKey: String(process.env.BAILEYS_API_KEY || "").trim(),
  authDirRoot: String(process.env.BAILEYS_AUTH_DIR || "/data/auth").trim(),
  connectWaitMs: Number.parseInt(process.env.BAILEYS_CONNECT_WAIT_MS || "12000", 10),
  pairingPhoneNumber: normalizePhoneNumber(process.env.BAILEYS_PAIRING_PHONE_NUMBER || ""),
  port: Number.parseInt(process.env.PORT || "3000", 10),
  webhookTimeoutMs: Number.parseInt(process.env.WHATSAPP_WEBHOOK_TIMEOUT_MS || "10000", 10),
  webhookUrl: String(process.env.WHATSAPP_WEBHOOK_URL || "").trim(),
};

const runtime = {
  connectWaiters: [],
  lastQrCode: null,
  lastQrDataUrl: null,
  pairingCode: null,
  sessionName: "",
  socket: null,
  socketBootPromise: null,
  state: "close",
};

app.use((request, response, next) => {
  if (request.path === "/health") {
    next();
    return;
  }
  if (!config.apiKey) {
    next();
    return;
  }
  if (request.headers.apikey === config.apiKey) {
    next();
    return;
  }
  response.status(401).json({
    status: 401,
    error: "Unauthorized",
  });
});

app.get("/health", (_, response) => {
  response.json({
    status: "ok",
    provider: "baileys",
    session: {
      name: runtime.sessionName || null,
      state: runtime.state,
      hasQr: Boolean(runtime.lastQrDataUrl),
      hasPairingCode: Boolean(runtime.pairingCode),
    },
    webhookConfigured: Boolean(config.webhookUrl),
  });
});

app.get("/instance/connectionState/:sessionName", async (request, response) => {
  const sessionName = resolveSessionName(request.params.sessionName);
  await ensureSocket(sessionName);
  response.json({
    instance: {
      instanceName: sessionName,
      state: runtime.state,
    },
  });
});

app.get("/instance/connect/:sessionName", async (request, response) => {
  const sessionName = resolveSessionName(request.params.sessionName);
  await ensureSocket(sessionName);
  await requestPairingCodeIfConfigured(sessionName);
  if (runtime.state !== "open" && !runtime.lastQrDataUrl && !runtime.pairingCode) {
    await waitForConnectArtifact(config.connectWaitMs);
  }
  response.json({
    pairingCode: runtime.pairingCode,
    code: runtime.lastQrCode,
    base64: runtime.lastQrDataUrl,
    count: runtime.lastQrDataUrl ? 1 : 0,
  });
});

app.post("/message/sendText/:sessionName", async (request, response) => {
  const sessionName = resolveSessionName(request.params.sessionName);
  const number = normalizePhoneNumber(request.body.number);
  const text = String(request.body.text || "").trim();

  if (!number || !text) {
    response.status(400).json({
      error: {
        message: "fields 'number' and 'text' are required",
      },
    });
    return;
  }

  await ensureSocket(sessionName);
  if (!runtime.socket || runtime.state !== "open") {
    response.status(500).json({
      status: 500,
      error: "Internal Server Error",
      response: {
        message: "Connection Closed",
      },
    });
    return;
  }

  try {
    const jid = `${number}@s.whatsapp.net`;
    const result = await runtime.socket.sendMessage(jid, { text });
    response.json({
      key: {
        id: result && result.key ? result.key.id : null,
      },
      messageId: result && result.key ? result.key.id : null,
    });
  } catch (error) {
    logger.error(
      {
        error: summarizeError(error),
        sessionName,
      },
      "baileys_send_text_failed",
    );
    response.status(500).json({
      status: 500,
      error: "Internal Server Error",
      response: {
        message: error instanceof Error ? error.message : "send_failed",
      },
    });
  }
});

async function bootstrapSocket(sessionName) {
  const authDir = path.join(config.authDirRoot, sessionName);
  fs.mkdirSync(authDir, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const versionInfo = await fetchLatestBaileysVersion().catch((error) => {
    logger.warn({ error: summarizeError(error) }, "baileys_version_lookup_failed");
    return null;
  });

  const socket = makeWASocket({
    auth: state,
    browser: Browsers.ubuntu("Chrome"),
    logger,
    markOnlineOnConnect: false,
    printQRInTerminal: false,
    syncFullHistory: false,
    version: Array.isArray(versionInfo && versionInfo.version) ? versionInfo.version : undefined,
  });

  socket.ev.on("creds.update", saveCreds);
  socket.ev.on("messages.upsert", async (payload) => {
    await forwardIncomingMessages(sessionName, payload);
  });
  socket.ev.on("connection.update", async (update) => {
    await handleConnectionUpdate(sessionName, update);
  });

  runtime.lastQrCode = null;
  runtime.lastQrDataUrl = null;
  runtime.pairingCode = null;
  runtime.sessionName = sessionName;
  runtime.socket = socket;
  runtime.state = "connecting";
}

async function ensureSocket(sessionName) {
  if (runtime.socket && runtime.sessionName === sessionName && runtime.state !== "close") {
    return;
  }
  if (runtime.socketBootPromise && runtime.sessionName === sessionName) {
    await runtime.socketBootPromise;
    return;
  }
  if (runtime.sessionName && runtime.sessionName !== sessionName) {
    throw buildHttpError(409, `session already initialized: ${runtime.sessionName}`);
  }

  runtime.sessionName = sessionName;
  runtime.socketBootPromise = bootstrapSocket(sessionName)
    .catch((error) => {
      runtime.state = "close";
      throw error;
    })
    .finally(() => {
      runtime.socketBootPromise = null;
    });
  await runtime.socketBootPromise;
}

function resolveSessionName(rawSessionName) {
  const sessionName = String(rawSessionName || "").trim();
  if (!sessionName) {
    throw buildHttpError(400, "sessionName is required");
  }
  return sessionName;
}

function normalizePhoneNumber(rawValue) {
  return String(rawValue || "").replace(/\D/g, "");
}

function summarizeError(error) {
  if (!error) {
    return "unknown_error";
  }
  if (error instanceof Error) {
    return `${error.name}: ${error.message}`;
  }
  return String(error);
}

function buildHttpError(statusCode, detail) {
  const error = new Error(detail);
  error.statusCode = statusCode;
  return error;
}

function notifyConnectWaiters() {
  const waiters = runtime.connectWaiters.splice(0, runtime.connectWaiters.length);
  for (const resolve of waiters) {
    resolve();
  }
}

async function waitForConnectArtifact(timeoutMs) {
  if (runtime.state === "open" || runtime.lastQrDataUrl || runtime.pairingCode) {
    return;
  }
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, timeoutMs);
    runtime.connectWaiters.push(() => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

async function requestPairingCodeIfConfigured(sessionName) {
  if (!config.pairingPhoneNumber || !runtime.socket || runtime.sessionName !== sessionName || runtime.pairingCode) {
    return;
  }
  if (runtime.state === "open") {
    return;
  }
  try {
    const code = await runtime.socket.requestPairingCode(config.pairingPhoneNumber);
    runtime.pairingCode = code || null;
    notifyConnectWaiters();
  } catch (error) {
    logger.warn(
      {
        error: summarizeError(error),
        sessionName,
      },
      "baileys_pairing_code_failed",
    );
  }
}

async function handleConnectionUpdate(sessionName, update) {
  if (runtime.sessionName !== sessionName) {
    return;
  }

  if (update.qr) {
    runtime.lastQrCode = update.qr;
    runtime.lastQrDataUrl = await QRCode.toDataURL(update.qr);
    runtime.state = "connecting";
    notifyConnectWaiters();
  }

  if (update.connection === "open") {
    runtime.state = "open";
    runtime.lastQrCode = null;
    runtime.lastQrDataUrl = null;
    runtime.pairingCode = null;
    notifyConnectWaiters();
    logger.info({ sessionName }, "baileys_connection_open");
    return;
  }

  if (update.connection === "close") {
    runtime.state = "close";
    runtime.socket = null;
    notifyConnectWaiters();

    const disconnectStatus = extractDisconnectStatusCode(update.lastDisconnect && update.lastDisconnect.error);
    logger.warn(
      {
        disconnectStatus,
        error: summarizeError(update.lastDisconnect && update.lastDisconnect.error),
        sessionName,
      },
      "baileys_connection_closed",
    );

    if (disconnectStatus !== DisconnectReason.loggedOut) {
      setTimeout(() => {
        ensureSocket(sessionName).catch((error) => {
          logger.error(
            {
              error: summarizeError(error),
              sessionName,
            },
            "baileys_reconnect_failed",
          );
        });
      }, 3000);
    }
  }
}

function extractDisconnectStatusCode(error) {
  if (!error) {
    return null;
  }
  if (error instanceof Boom && error.output && typeof error.output.statusCode === "number") {
    return error.output.statusCode;
  }
  if (error.output && typeof error.output.statusCode === "number") {
    return error.output.statusCode;
  }
  return null;
}

function unwrapMessageContent(message) {
  if (!message || typeof message !== "object") {
    return {};
  }
  if (message.ephemeralMessage && message.ephemeralMessage.message) {
    return unwrapMessageContent(message.ephemeralMessage.message);
  }
  if (message.viewOnceMessage && message.viewOnceMessage.message) {
    return unwrapMessageContent(message.viewOnceMessage.message);
  }
  if (message.viewOnceMessageV2 && message.viewOnceMessageV2.message) {
    return unwrapMessageContent(message.viewOnceMessageV2.message);
  }
  if (message.imageMessage && message.imageMessage.caption) {
    return {
      ...message,
      extendedTextMessage: {
        text: message.imageMessage.caption,
      },
    };
  }
  if (message.videoMessage && message.videoMessage.caption) {
    return {
      ...message,
      extendedTextMessage: {
        text: message.videoMessage.caption,
      },
    };
  }
  if (message.documentMessage && message.documentMessage.caption) {
    return {
      ...message,
      extendedTextMessage: {
        text: message.documentMessage.caption,
      },
    };
  }
  return message;
}

async function forwardIncomingMessages(sessionName, payload) {
  if (!config.webhookUrl) {
    return;
  }

  const rows = Array.isArray(payload && payload.messages) ? payload.messages : [];
  const data = rows
    .filter((message) => message && message.key && !message.key.fromMe)
    .map((message) => ({
      key: {
        id: message.key && message.key.id ? message.key.id : null,
        remoteJid: message.key && message.key.remoteJid ? message.key.remoteJid : null,
        fromMe: Boolean(message.key && message.key.fromMe),
      },
      message: unwrapMessageContent(message.message),
      pushName: message.pushName || message.notifyName || null,
      senderName: message.pushName || message.notifyName || null,
      sessionName,
    }))
    .filter((row) => row.key.remoteJid && Object.keys(row.message).length > 0);

  if (!data.length) {
    return;
  }

  const body = {
    event: "messages.upsert",
    data,
    provider: "baileys",
    type: payload && payload.type ? payload.type : null,
  };

  try {
    const abortController = new AbortController();
    const timeout = setTimeout(() => {
      abortController.abort();
    }, config.webhookTimeoutMs);
    const result = await fetch(config.webhookUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-WhatsApp-Provider": "baileys",
      },
      body: JSON.stringify(body),
      signal: abortController.signal,
    });
    clearTimeout(timeout);
    if (!result.ok) {
      logger.warn(
        {
          sessionName,
          statusCode: result.status,
        },
        "baileys_webhook_forward_non_2xx",
      );
    }
  } catch (error) {
    logger.error(
      {
        error: summarizeError(error),
        sessionName,
      },
      "baileys_webhook_forward_failed",
    );
  }
}

app.use((error, _, response, __) => {
  const statusCode = typeof error.statusCode === "number" ? error.statusCode : 500;
  logger.error(
    {
      error: summarizeError(error),
      statusCode,
    },
    "baileys_gateway_request_failed",
  );
  response.status(statusCode).json({
    status: statusCode,
    error: statusCode >= 500 ? "Internal Server Error" : "Request Error",
    response: {
      message: error.message || "unexpected_error",
    },
  });
});

app.listen(config.port, () => {
  logger.info(
    {
      port: config.port,
      webhookConfigured: Boolean(config.webhookUrl),
    },
    "baileys_gateway_listening",
  );
});
