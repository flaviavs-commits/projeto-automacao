const fs = require("fs");
const path = require("path");
const os = require("os");

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
} = require("@whiskeysockets/baileys");

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  base: null,
});

const app = express();
app.use(express.json({ limit: "1mb" }));

const gatewayStartedAt = new Date().toISOString();
const disconnectReasonLookup = new Map(
  Object.entries(DisconnectReason)
    .filter(([, value]) => typeof value === "number")
    .map(([key, value]) => [value, key]),
);

const config = {
  apiKey: String(process.env.BAILEYS_API_KEY || "").trim(),
  authDirRoot: path.resolve(String(process.env.BAILEYS_AUTH_DIR || "/data/auth").trim()),
  connectWaitMs: Number.parseInt(process.env.BAILEYS_CONNECT_WAIT_MS || "12000", 10),
  pairingCodeDelayMs: Number.parseInt(process.env.BAILEYS_PAIRING_CODE_DELAY_MS || "2000", 10),
  pairingCodeTtlMs: Number.parseInt(process.env.BAILEYS_PAIRING_CODE_TTL_MS || "90000", 10),
  pairingPhoneNumber: normalizePhoneNumber(process.env.BAILEYS_PAIRING_PHONE_NUMBER || ""),
  port: Number.parseInt(process.env.PORT || "3000", 10),
  reconnectBaseDelayMs: Number.parseInt(process.env.BAILEYS_RECONNECT_BASE_DELAY_MS || "5000", 10),
  reconnectMaxDelayMs: Number.parseInt(process.env.BAILEYS_RECONNECT_MAX_DELAY_MS || "60000", 10),
  webhookTimeoutMs: Number.parseInt(process.env.WHATSAPP_WEBHOOK_TIMEOUT_MS || "10000", 10),
  webhookUrl: String(process.env.WHATSAPP_WEBHOOK_URL || "").trim(),
};

const runtime = {
  pid: process.pid,
  provider: "baileys",
  startedAt: gatewayStartedAt,
  hostname: os.hostname(),
  sessions: new Map(),
  versionPromise: null,
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
    provider: runtime.provider,
    pid: runtime.pid,
    startedAt: runtime.startedAt,
    hostname: runtime.hostname,
    authDirRoot: config.authDirRoot,
    authDirRootExists: fs.existsSync(config.authDirRoot),
    webhookConfigured: Boolean(config.webhookUrl),
    sessions: Array.from(runtime.sessions.values()).map((session) => buildSessionSnapshot(session)),
  });
});

app.get("/instance/connectionState/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);
  response.json({
    instance: {
      instanceName: session.sessionName,
      state: session.state,
    },
    session: buildSessionSnapshot(session),
  });
});

app.get("/whatsapp/status/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);
  response.json(buildSessionSnapshot(session));
});

app.get("/instance/connect/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);

  if (session.state === "open") {
    response.json(buildConnectPayload(session, "session already connected"));
    return;
  }

  if (session.state === "logged_out") {
    response.status(409).json(
      buildConnectPayload(
        session,
        "session is logged out; call POST /instance/reset-session/:sessionName before pairing again",
      ),
    );
    return;
  }

  if (session.state === "qr_expired") {
    response.status(409).json(
      buildConnectPayload(
        session,
        "pairing expired; call POST /instance/restart/:sessionName to generate a new QR",
      ),
    );
    return;
  }

  if (!session.socket && !session.socketBootPromise) {
    await startSession(session.sessionName, {
      allowFromExpiredState: false,
      force: false,
      source: "manual_connect",
    });
  }

  const preferPairingCode = Boolean(config.pairingPhoneNumber);
  const shouldWaitForArtifact = preferPairingCode
    ? session.state !== "open" && !session.pairingCode && session.state !== "logged_out" && session.state !== "qr_expired"
    : session.state !== "open" && !session.qrAvailable && !session.pairingCode;

  if (shouldWaitForArtifact) {
    await waitForConnectArtifact(session, config.connectWaitMs, {
      preferPairingCode,
    });
  }

  if (session.state === "qr_expired") {
    response.status(409).json(
      buildConnectPayload(
        session,
        "pairing expired; call POST /instance/restart/:sessionName to generate a new QR",
      ),
    );
    return;
  }

  if (session.state === "logged_out") {
    response.status(409).json(
      buildConnectPayload(
        session,
        "session is logged out; call POST /instance/reset-session/:sessionName before pairing again",
      ),
    );
    return;
  }

  response.json(buildConnectPayload(session));
});

app.get("/whatsapp/qr/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);

  if (session.state === "open") {
    response.json(buildConnectPayload(session, "session already connected"));
    return;
  }

  if (session.qrAvailable || session.pairingCode) {
    response.json(buildConnectPayload(session));
    return;
  }

  if (session.state === "qr_expired") {
    response.status(409).json(
      buildConnectPayload(
        session,
        "pairing expired; call POST /instance/restart/:sessionName to generate a new QR",
      ),
    );
    return;
  }

  response.status(404).json({
    session: session.sessionName,
    state: session.state,
    message: "no live QR available; call GET /instance/connect/:sessionName to start pairing",
  });
});

app.get("/whatsapp/pairing-code/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);

  if (session.state === "open") {
    response.json({
      session: session.sessionName,
      state: session.state,
      message: "session already connected",
      pairingCode: null,
      sessionInfo: buildSessionSnapshot(session),
    });
    return;
  }

  if (session.state === "logged_out") {
    response.status(409).json({
      session: session.sessionName,
      state: session.state,
      message: "session is logged out; call POST /instance/reset-session/:sessionName before pairing again",
      pairingCode: null,
      sessionInfo: buildSessionSnapshot(session),
    });
    return;
  }

  if (!config.pairingPhoneNumber) {
    response.status(409).json({
      session: session.sessionName,
      state: session.state,
      message: "phone pairing is not configured; set BAILEYS_PAIRING_PHONE_NUMBER first",
      pairingCode: null,
      sessionInfo: buildSessionSnapshot(session),
    });
    return;
  }

  if (hasLivePairingCode(session)) {
    response.json({
      session: session.sessionName,
      state: session.state,
      message: null,
      pairingCode: session.pairingCode,
      pairingCodeRequestedAt: session.pairingCodeRequestedAt,
      pairingCodeExpiresAt: session.pairingCodeExpiresAt,
      sessionInfo: buildSessionSnapshot(session),
    });
    return;
  }

  response.status(404).json({
    session: session.sessionName,
    state: session.state,
    message: "no live pairing code available; call GET /instance/connect/:sessionName to start pairing",
    pairingCode: null,
    sessionInfo: buildSessionSnapshot(session),
  });
});

app.post("/instance/restart/:sessionName", requireControlApiKey, async (request, response) => {
  const session = getSession(request.params.sessionName);
  await restartSession(session.sessionName);
  if (session.state !== "open" && !session.qrAvailable && !session.pairingCode) {
    await waitForConnectArtifact(session, config.connectWaitMs);
  }
  response.json({
    action: "restart",
    sessionInfo: buildSessionSnapshot(session),
    ...buildConnectPayload(session),
  });
});

app.post("/instance/reset-session/:sessionName", requireControlApiKey, async (request, response) => {
  const session = getSession(request.params.sessionName);
  const authDir = session.authDir;
  await resetSession(session.sessionName);
  response.json({
    action: "reset_session",
    message: "session auth removed; call GET /instance/connect/:sessionName to start a single new pairing attempt",
    session: buildSessionSnapshot(session),
    authDir,
  });
});

app.post("/message/sendText/:sessionName", async (request, response) => {
  const session = getSession(request.params.sessionName);
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

  if (!session.socket || session.state !== "open") {
    response.status(500).json({
      status: 500,
      error: "Internal Server Error",
      response: {
        message: `session_not_open:${session.state || "close"}`,
      },
      session: buildSessionSnapshot(session),
    });
    return;
  }

  try {
    const jid = `${number}@s.whatsapp.net`;
    const result = await session.socket.sendMessage(jid, { text });
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
        sessionName: session.sessionName,
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

function requireControlApiKey(request, response, next) {
  if (!config.apiKey) {
    response.status(503).json({
      status: 503,
      error: "Service Unavailable",
      response: {
        message: "BAILEYS_API_KEY is required for restart/reset endpoints",
      },
    });
    return;
  }
  if (request.headers.apikey !== config.apiKey) {
    response.status(401).json({
      status: 401,
      error: "Unauthorized",
    });
    return;
  }
  next();
}

function getSession(rawSessionName) {
  const sessionName = resolveSessionName(rawSessionName);
  let session = runtime.sessions.get(sessionName);
  if (!session) {
    session = createSessionRuntime(sessionName);
    runtime.sessions.set(sessionName, session);
  }
  refreshAuthMetadata(session);
  return session;
}

function createSessionRuntime(sessionName) {
  return {
    authDir: buildSessionAuthDir(sessionName),
    authDirExists: false,
    authFileCount: 0,
    connection: "close",
    connectWaiters: [],
    isAuthenticated: false,
    lastDisconnectAt: null,
    lastDisconnectReason: null,
    lastDisconnectStatus: null,
    lockFile: buildSessionLockFile(sessionName),
    manualStop: false,
    pairingCode: null,
    pairingCodeExpiresAt: null,
    pairingCodeRequestInFlight: false,
    pairingCodeRequestScheduledAt: null,
    pairingCodeRequestedAt: null,
    pairingCodeTimer: null,
    pid: runtime.pid,
    qrAvailable: false,
    qrCode: null,
    qrDataUrl: null,
    qrExpiresAt: null,
    qrGeneratedAt: null,
    reconnectAttempts: 0,
    reconnectTimer: null,
    sessionName,
    socket: null,
    socketAuthState: null,
    socketBootPromise: null,
    socketGeneration: 0,
    startedAt: runtime.startedAt,
    state: "idle",
  };
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

function buildSessionAuthDir(sessionName) {
  return path.join(config.authDirRoot, sessionName);
}

function buildSessionLockFile(sessionName) {
  return path.join(config.authDirRoot, `.${sessionName}.lock.json`);
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

function ensureDirectory(targetDir) {
  fs.mkdirSync(targetDir, { recursive: true });
}

function refreshAuthMetadata(session) {
  session.authDirExists = fs.existsSync(session.authDir);
  session.authFileCount = session.authDirExists ? countFilesRecursive(session.authDir) : 0;
}

function countFilesRecursive(targetDir) {
  let count = 0;
  const entries = fs.readdirSync(targetDir, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      count += countFilesRecursive(entryPath);
      continue;
    }
    if (entry.isFile()) {
      count += 1;
    }
  }
  return count;
}

function notifyConnectWaiters(session) {
  const waiters = session.connectWaiters.splice(0, session.connectWaiters.length);
  for (const resolve of waiters) {
    resolve();
  }
}

function shouldStopWaitingForArtifact(session, preferPairingCode) {
  if (session.state === "open" || hasLivePairingCode(session) || session.state === "qr_expired" || session.state === "logged_out") {
    return true;
  }
  if (!preferPairingCode && session.qrAvailable) {
    return true;
  }
  return false;
}

async function waitForConnectArtifact(session, timeoutMs, options = {}) {
  const preferPairingCode = Boolean(options.preferPairingCode);
  if (shouldStopWaitingForArtifact(session, preferPairingCode)) {
    return;
  }
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, timeoutMs);
    session.connectWaiters.push(() => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

function clearReconnectTimer(session) {
  if (session.reconnectTimer) {
    clearTimeout(session.reconnectTimer);
    session.reconnectTimer = null;
  }
}

function clearPairingCodeTimer(session) {
  if (session.pairingCodeTimer) {
    clearTimeout(session.pairingCodeTimer);
    session.pairingCodeTimer = null;
  }
  session.pairingCodeRequestScheduledAt = null;
}

function clearPairingCode(session) {
  session.pairingCode = null;
  session.pairingCodeExpiresAt = null;
  session.pairingCodeRequestedAt = null;
}

function hasLivePairingCode(session) {
  if (!session.pairingCode || !session.pairingCodeExpiresAt) {
    return false;
  }

  const expiresAtMs = Date.parse(session.pairingCodeExpiresAt);
  if (!Number.isFinite(expiresAtMs)) {
    clearPairingCode(session);
    return false;
  }

  if (Date.now() >= expiresAtMs) {
    logger.info(
      {
        pairingCodeExpiresAt: session.pairingCodeExpiresAt,
        sessionName: session.sessionName,
      },
      "baileys_pairing_code_expired",
    );
    clearPairingCode(session);
    return false;
  }

  return true;
}

function writeSessionLock(session) {
  ensureDirectory(config.authDirRoot);
  const lockPayload = {
    hostname: runtime.hostname,
    pid: runtime.pid,
    provider: runtime.provider,
    sessionName: session.sessionName,
    startedAt: runtime.startedAt,
    updatedAt: new Date().toISOString(),
  };

  if (fs.existsSync(session.lockFile)) {
    try {
      const existing = JSON.parse(fs.readFileSync(session.lockFile, "utf8"));
      if (existing && existing.pid && Number(existing.pid) !== runtime.pid) {
        logger.warn(
          {
            existingLockHostname: existing.hostname || null,
            existingLockPid: existing.pid,
            existingLockStartedAt: existing.startedAt || null,
            lockFile: session.lockFile,
            sessionName: session.sessionName,
          },
          "baileys_session_lockfile_present",
        );
      }
    } catch (error) {
      logger.warn(
        {
          error: summarizeError(error),
          lockFile: session.lockFile,
          sessionName: session.sessionName,
        },
        "baileys_session_lockfile_read_failed",
      );
    }
  }

  fs.writeFileSync(session.lockFile, `${JSON.stringify(lockPayload, null, 2)}\n`, "utf8");
}

function removeSessionLock(session) {
  try {
    fs.rmSync(session.lockFile, { force: true });
  } catch (error) {
    logger.warn(
      {
        error: summarizeError(error),
        lockFile: session.lockFile,
        sessionName: session.sessionName,
      },
      "baileys_session_lockfile_remove_failed",
    );
  }
}

async function getBaileysVersion() {
  if (!runtime.versionPromise) {
    runtime.versionPromise = fetchLatestBaileysVersion()
      .then((versionInfo) => (Array.isArray(versionInfo && versionInfo.version) ? versionInfo.version : undefined))
      .catch((error) => {
        logger.warn({ error: summarizeError(error) }, "baileys_version_lookup_failed");
        return undefined;
      });
  }
  return runtime.versionPromise;
}

async function startSession(sessionName, options = {}) {
  const session = getSession(sessionName);
  const allowFromExpiredState = Boolean(options.allowFromExpiredState);
  const force = Boolean(options.force);
  const source = String(options.source || "manual_start");

  if (session.socketBootPromise) {
    await session.socketBootPromise;
    return session;
  }

  if (session.socket && (session.state === "connecting" || session.state === "open")) {
    logger.info(
      {
        sessionName: session.sessionName,
        source,
        state: session.state,
      },
      "baileys_start_skipped_existing_socket",
    );
    return session;
  }

  if (!force && (session.state === "qr_expired" || session.state === "logged_out")) {
    logger.info(
      {
        blockedState: session.state,
        sessionName: session.sessionName,
        source,
      },
      "baileys_start_blocked_state",
    );
    return session;
  }

  if (!allowFromExpiredState && session.state === "qr_expired") {
    logger.info(
      {
        blockedState: session.state,
        sessionName: session.sessionName,
        source,
      },
      "baileys_start_blocked_qr_expired",
    );
    return session;
  }

  clearReconnectTimer(session);
  ensureDirectory(config.authDirRoot);
  ensureDirectory(session.authDir);
  refreshAuthMetadata(session);
  writeSessionLock(session);

  const generation = session.socketGeneration + 1;
  session.socketGeneration = generation;
  session.connection = "connecting";
  session.manualStop = false;
  clearPairingCode(session);
  session.pairingCodeRequestInFlight = false;
  session.qrAvailable = false;
  session.qrCode = null;
  session.qrDataUrl = null;
  session.qrExpiresAt = null;
  session.state = "connecting";
  clearPairingCodeTimer(session);

  logger.info(
    {
      authDir: session.authDir,
      authDirExists: session.authDirExists,
      authFileCount: session.authFileCount,
      pid: runtime.pid,
      sessionName: session.sessionName,
      source,
    },
    "baileys_session_bootstrap_start",
  );

  const bootPromise = bootstrapSocket(session, generation)
    .catch((error) => {
      session.connection = "close";
      session.socket = null;
      session.state = session.state === "qr_expired" ? session.state : "close";
      throw error;
    })
    .finally(() => {
      if (session.socketBootPromise === bootPromise) {
        session.socketBootPromise = null;
      }
    });

  session.socketBootPromise = bootPromise;
  await bootPromise;
  return session;
}

async function bootstrapSocket(session, generation) {
  const { state: authState, saveCreds } = await useMultiFileAuthState(session.authDir);
  const version = await getBaileysVersion();

  session.isAuthenticated = Boolean(authState && authState.creds && authState.creds.registered);
  session.socketAuthState = authState;

  const socket = makeWASocket({
    auth: authState,
    browser: Browsers.ubuntu("Chrome"),
    logger,
    markOnlineOnConnect: false,
    printQRInTerminal: false,
    syncFullHistory: false,
    version,
  });

  socket.ev.on("creds.update", async () => {
    await saveCreds();
    session.isAuthenticated = Boolean(authState && authState.creds && authState.creds.registered);
    refreshAuthMetadata(session);
    logger.info(
      {
        authDir: session.authDir,
        authDirExists: session.authDirExists,
        authFileCount: session.authFileCount,
        isAuthenticated: session.isAuthenticated,
        sessionName: session.sessionName,
      },
      "baileys_creds_updated",
    );
  });

  socket.ev.on("messages.upsert", async (payload) => {
    await handleMessagesUpsert(session, generation, payload);
  });

  socket.ev.on("connection.update", async (update) => {
    await handleConnectionUpdate(session, generation, update);
  });

  if (generation !== session.socketGeneration) {
    try {
      if (typeof socket.end === "function") {
        socket.end(new Boom("stale_socket_generation", { statusCode: DisconnectReason.restartRequired }));
      } else if (socket.ws && typeof socket.ws.close === "function") {
        socket.ws.close();
      }
    } catch (error) {
      logger.warn(
        {
          error: summarizeError(error),
          sessionName: session.sessionName,
        },
        "baileys_stale_socket_close_failed",
      );
    }
    return;
  }

  session.socket = socket;
}

async function requestPairingCodeIfConfigured(session, trigger = "manual") {
  if (
    !config.pairingPhoneNumber
    || !session.socket
    || hasLivePairingCode(session)
    || session.state === "open"
    || session.pairingCodeRequestInFlight
  ) {
    return;
  }
  clearPairingCode(session);
  session.pairingCodeRequestInFlight = true;
  try {
    const code = await session.socket.requestPairingCode(config.pairingPhoneNumber);
    session.pairingCode = code || null;
    session.pairingCodeRequestedAt = new Date().toISOString();
    session.pairingCodeExpiresAt = new Date(Date.now() + config.pairingCodeTtlMs).toISOString();
    notifyConnectWaiters(session);
    logger.info(
      {
        pairingCodeExpiresAt: session.pairingCodeExpiresAt,
        pairingCodeRequestedAt: session.pairingCodeRequestedAt,
        sessionName: session.sessionName,
        trigger,
      },
      "baileys_pairing_code_received",
    );
  } catch (error) {
    logger.warn(
      {
        error: summarizeError(error),
        sessionName: session.sessionName,
        trigger,
      },
      "baileys_pairing_code_failed",
    );
  } finally {
    session.pairingCodeRequestInFlight = false;
  }
}

function schedulePairingCodeRequest(session, trigger) {
  if (
    !config.pairingPhoneNumber
    || hasLivePairingCode(session)
    || session.pairingCodeRequestInFlight
    || session.pairingCodeTimer
    || session.state === "open"
    || session.state === "logged_out"
    || !session.socket
  ) {
    return;
  }

  session.pairingCodeRequestScheduledAt = new Date().toISOString();
  session.pairingCodeTimer = setTimeout(() => {
    session.pairingCodeTimer = null;
    session.pairingCodeRequestScheduledAt = null;
    requestPairingCodeIfConfigured(session, trigger).catch((error) => {
      logger.warn(
        {
          error: summarizeError(error),
          sessionName: session.sessionName,
          trigger,
        },
        "baileys_pairing_code_request_unhandled",
      );
    });
  }, config.pairingCodeDelayMs);

  logger.info(
    {
      delayMs: config.pairingCodeDelayMs,
      sessionName: session.sessionName,
      trigger,
    },
    "baileys_pairing_code_scheduled",
  );
}

async function handleConnectionUpdate(session, generation, update) {
  if (generation !== session.socketGeneration) {
    return;
  }

  if (update.connection) {
    session.connection = update.connection;
  }

  if (update.qr) {
    if (session.qrGeneratedAt && hasLivePairingCode(session)) {
      logger.info(
        {
          pairingCodeExpiresAt: session.pairingCodeExpiresAt,
          pairingCodeRequestedAt: session.pairingCodeRequestedAt,
          qrGeneratedAt: new Date().toISOString(),
          sessionName: session.sessionName,
        },
        "baileys_qr_rotated_pairing_code_still_cached",
      );
    }
    session.qrCode = update.qr;
    session.qrDataUrl = await QRCode.toDataURL(update.qr);
    session.qrAvailable = true;
    session.qrGeneratedAt = new Date().toISOString();
    session.qrExpiresAt = null;
    session.state = "connecting";
    notifyConnectWaiters(session);
    logger.info(
      {
        qrGeneratedAt: session.qrGeneratedAt,
        sessionName: session.sessionName,
      },
      "baileys_qr_generated",
    );
    schedulePairingCodeRequest(session, "qr");
  }

  if (update.connection === "connecting") {
    schedulePairingCodeRequest(session, "connecting");
  }

  if (update.connection === "open") {
    session.connection = "open";
    session.isAuthenticated = true;
    session.lastDisconnectAt = null;
    session.lastDisconnectReason = null;
    session.lastDisconnectStatus = null;
    clearPairingCode(session);
    session.qrAvailable = false;
    session.qrCode = null;
    session.qrDataUrl = null;
    session.qrExpiresAt = null;
    session.reconnectAttempts = 0;
    session.state = "open";
    clearPairingCodeTimer(session);
    session.pairingCodeRequestInFlight = false;
    refreshAuthMetadata(session);
    writeSessionLock(session);
    notifyConnectWaiters(session);
    logger.info(
      {
        authDir: session.authDir,
        authDirExists: session.authDirExists,
        authFileCount: session.authFileCount,
        sessionName: session.sessionName,
      },
      "baileys_connection_open",
    );
    return;
  }

  if (update.connection === "close") {
    const disconnect = classifyDisconnect(session, update.lastDisconnect && update.lastDisconnect.error);
    session.connection = "close";
    session.lastDisconnectAt = new Date().toISOString();
    session.lastDisconnectReason = disconnect.reason;
    session.lastDisconnectStatus = disconnect.status;
    session.socket = null;
    clearPairingCode(session);
    clearPairingCodeTimer(session);
    session.pairingCodeRequestInFlight = false;
    session.qrAvailable = false;
    session.qrCode = null;
    session.qrDataUrl = null;
    notifyConnectWaiters(session);

    logger.warn(
      {
        disconnectDetail: disconnect.detail,
        disconnectReason: disconnect.reason,
        disconnectStatus: disconnect.status,
        isAuthenticated: session.isAuthenticated,
        reconnectAttempts: session.reconnectAttempts,
        sessionName: session.sessionName,
      },
      "baileys_connection_closed",
    );

    if (session.manualStop) {
      session.manualStop = false;
      if (session.state !== "reset") {
        session.state = "close";
      }
      logger.info(
        {
          sessionName: session.sessionName,
          state: session.state,
        },
        "baileys_connection_closed_manual_stop",
      );
      return;
    }

    if (disconnect.category === "logged_out") {
      clearReconnectTimer(session);
      session.isAuthenticated = false;
      session.state = "logged_out";
      logger.warn(
        {
          sessionName: session.sessionName,
        },
        "baileys_logged_out_manual_reset_required",
      );
      return;
    }

    if (disconnect.category === "qr_expired") {
      clearReconnectTimer(session);
      session.state = "qr_expired";
      session.qrExpiresAt = session.lastDisconnectAt;
      logger.warn(
        {
          qrExpiredAt: session.qrExpiresAt,
          sessionName: session.sessionName,
        },
        "baileys_qr_expired_reconnect_blocked",
      );
      return;
    }

    if (disconnect.category === "reconnect" && session.isAuthenticated) {
      scheduleReconnect(session, disconnect);
      return;
    }

    clearReconnectTimer(session);
    session.state = "close";
    logger.info(
      {
        disconnectDetail: disconnect.detail,
        disconnectReason: disconnect.reason,
        disconnectStatus: disconnect.status,
        sessionName: session.sessionName,
      },
      "baileys_reconnect_blocked",
    );
  }
}

function classifyDisconnect(session, error) {
  const status = extractDisconnectStatusCode(error);
  const detail = summarizeError(error).toLowerCase();
  const statusReason = status != null ? disconnectReasonLookup.get(status) || `status_${status}` : null;

  if (status === DisconnectReason.loggedOut || detail.includes("logged out")) {
    return {
      category: "logged_out",
      detail,
      reason: "logged_out",
      status,
    };
  }

  if (
    !session.isAuthenticated &&
    (status === 408 || detail.includes("qr refs attempts ended") || detail.includes("pairing timed out"))
  ) {
    return {
      category: "qr_expired",
      detail,
      reason: detail.includes("qr refs attempts ended") ? "qr_refs_attempts_ended" : "qr_expired",
      status,
    };
  }

  if (session.isAuthenticated && isReconnectableDisconnect(status, detail)) {
    return {
      category: "reconnect",
      detail,
      reason: statusReason || "transient_disconnect",
      status,
    };
  }

  return {
    category: "close",
    detail,
    reason: statusReason || detail || "connection_closed",
    status,
  };
}

function isReconnectableDisconnect(status, detail) {
  if (status === 503) {
    return true;
  }

  const reconnectableStatuses = new Set([
    DisconnectReason.connectionClosed,
    DisconnectReason.connectionLost,
    DisconnectReason.restartRequired,
    DisconnectReason.timedOut,
  ]);

  if (status != null && reconnectableStatuses.has(status)) {
    return true;
  }

  return detail.includes("stream errored out") || detail.includes("timed out");
}

function scheduleReconnect(session, disconnect) {
  clearReconnectTimer(session);
  session.reconnectAttempts += 1;
  session.state = "reconnecting";

  const delayMs = Math.min(
    config.reconnectBaseDelayMs * Math.max(1, 2 ** (session.reconnectAttempts - 1)),
    config.reconnectMaxDelayMs,
  );

  logger.warn(
    {
      delayMs,
      disconnectDetail: disconnect.detail,
      disconnectReason: disconnect.reason,
      disconnectStatus: disconnect.status,
      reconnectAttempts: session.reconnectAttempts,
      sessionName: session.sessionName,
    },
    "baileys_reconnect_scheduled",
  );

  session.reconnectTimer = setTimeout(() => {
    session.reconnectTimer = null;
    startSession(session.sessionName, {
      allowFromExpiredState: false,
      force: true,
      source: "auto_reconnect",
    }).catch((error) => {
      logger.error(
        {
          error: summarizeError(error),
          sessionName: session.sessionName,
        },
        "baileys_reconnect_failed",
      );
    });
  }, delayMs);
}

async function stopSessionSocket(session, reason, nextState) {
  clearReconnectTimer(session);
  clearPairingCodeTimer(session);
  session.manualStop = true;
  session.state = nextState || session.state;
  session.qrAvailable = false;
  clearPairingCode(session);
  session.pairingCodeRequestInFlight = false;
  session.socketGeneration += 1;
  session.socketBootPromise = null;
  notifyConnectWaiters(session);

  if (!session.socket) {
    session.connection = "close";
    return;
  }

  const socket = session.socket;
  session.socket = null;

  try {
    if (typeof socket.end === "function") {
      socket.end(new Boom(reason, { statusCode: DisconnectReason.restartRequired }));
    } else if (socket.ws && typeof socket.ws.close === "function") {
      socket.ws.close();
    }
  } catch (error) {
    logger.warn(
      {
        error: summarizeError(error),
        reason,
        sessionName: session.sessionName,
      },
      "baileys_socket_stop_failed",
    );
  }

  session.connection = "close";
}

async function restartSession(sessionName) {
  const session = getSession(sessionName);
  await stopSessionSocket(session, "manual_restart", "close");
  session.qrExpiresAt = null;
  session.lastDisconnectAt = null;
  session.lastDisconnectReason = null;
  session.lastDisconnectStatus = null;
  session.reconnectAttempts = 0;
  await startSession(session.sessionName, {
    allowFromExpiredState: true,
    force: true,
    source: "manual_restart",
  });
}

async function resetSession(sessionName) {
  const session = getSession(sessionName);
  await stopSessionSocket(session, "manual_reset", "reset");
  clearReconnectTimer(session);
  removeSessionLock(session);
  safeRemoveAuthDir(session);

  session.connection = "close";
  session.isAuthenticated = false;
  session.lastDisconnectAt = null;
  session.lastDisconnectReason = null;
  session.lastDisconnectStatus = null;
  clearPairingCode(session);
  session.pairingCodeRequestInFlight = false;
  session.qrAvailable = false;
  session.qrCode = null;
  session.qrDataUrl = null;
  session.qrExpiresAt = null;
  session.qrGeneratedAt = null;
  session.reconnectAttempts = 0;
  session.state = "reset";
  refreshAuthMetadata(session);

  logger.warn(
    {
      authDir: session.authDir,
      authDirExists: session.authDirExists,
      authFileCount: session.authFileCount,
      sessionName: session.sessionName,
    },
    "baileys_session_reset_completed",
  );
}

function safeRemoveAuthDir(session) {
  const resolvedRoot = path.resolve(config.authDirRoot);
  const resolvedAuthDir = path.resolve(session.authDir);

  if (resolvedAuthDir === resolvedRoot || !resolvedAuthDir.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw buildHttpError(500, "refusing to remove auth dir outside configured root");
  }

  fs.rmSync(resolvedAuthDir, { force: true, recursive: true });
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

function buildSessionSnapshot(session) {
  refreshAuthMetadata(session);
  const pairingCodeActive = hasLivePairingCode(session);
  return {
    session: session.sessionName,
    state: session.state,
    connection: session.connection,
    isAuthenticated: session.isAuthenticated,
    pairingCodeActive,
    qrAvailable: session.qrAvailable,
    qrGeneratedAt: session.qrGeneratedAt,
    qrExpiresAt: session.qrExpiresAt,
    pairingCodeExpiresAt: session.pairingCodeExpiresAt,
    pairingCodeRequestedAt: session.pairingCodeRequestedAt,
    pairingCodeRequestScheduledAt: session.pairingCodeRequestScheduledAt,
    lastDisconnectAt: session.lastDisconnectAt,
    lastDisconnectReason: session.lastDisconnectReason,
    lastDisconnectStatus: session.lastDisconnectStatus,
    reconnectAttempts: session.reconnectAttempts,
    authDir: session.authDir,
    authDirExists: session.authDirExists,
    authFileCount: session.authFileCount,
    pid: session.pid,
    startedAt: session.startedAt,
  };
}

function buildConnectPayload(session, message = null) {
  const pairingCodeActive = hasLivePairingCode(session);
  return {
    session: session.sessionName,
    state: session.state,
    message,
    pairingCode: pairingCodeActive ? session.pairingCode : null,
    pairingCodeExpiresAt: pairingCodeActive ? session.pairingCodeExpiresAt : null,
    pairingCodeRequestedAt: pairingCodeActive ? session.pairingCodeRequestedAt : null,
    code: session.qrCode,
    base64: session.qrDataUrl,
    count: session.qrDataUrl ? 1 : 0,
    sessionInfo: buildSessionSnapshot(session),
  };
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

async function handleMessagesUpsert(session, generation, payload) {
  if (generation !== session.socketGeneration) {
    return;
  }
  await forwardIncomingMessages(session.sessionName, payload);
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
        remoteJidAlt: message.key && message.key.remoteJidAlt ? message.key.remoteJidAlt : null,
        participant: message.key && message.key.participant ? message.key.participant : null,
        participantPn: message.key && message.key.participantPn ? message.key.participantPn : null,
        participantLid: message.key && message.key.participantLid ? message.key.participantLid : null,
        senderPn: message.key && message.key.senderPn ? message.key.senderPn : null,
        senderLid: message.key && message.key.senderLid ? message.key.senderLid : null,
        fromMe: Boolean(message.key && message.key.fromMe),
      },
      message: unwrapMessageContent(message.message),
      pushName: message.pushName || message.notifyName || null,
      senderName: message.pushName || message.notifyName || null,
      remoteJidAlt: message.key && message.key.remoteJidAlt ? message.key.remoteJidAlt : null,
      participant: message.key && message.key.participant ? message.key.participant : null,
      participantPn: message.key && message.key.participantPn ? message.key.participantPn : null,
      participantLid: message.key && message.key.participantLid ? message.key.participantLid : null,
      senderPn: message.key && message.key.senderPn ? message.key.senderPn : null,
      senderLid: message.key && message.key.senderLid ? message.key.senderLid : null,
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

function cleanupLocks() {
  for (const session of runtime.sessions.values()) {
    removeSessionLock(session);
  }
}

process.once("SIGINT", () => {
  cleanupLocks();
  process.exit(0);
});

process.once("SIGTERM", () => {
  cleanupLocks();
  process.exit(0);
});

process.once("exit", cleanupLocks);

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

logger.info(
  {
    authDirRoot: config.authDirRoot,
    authDirRootExists: fs.existsSync(config.authDirRoot),
    hostname: runtime.hostname,
    pid: runtime.pid,
    provider: runtime.provider,
    startedAt: runtime.startedAt,
    webhookConfigured: Boolean(config.webhookUrl),
  },
  "baileys_gateway_starting",
);

app.listen(config.port, () => {
  logger.info(
    {
      authDirRoot: config.authDirRoot,
      authDirRootExists: fs.existsSync(config.authDirRoot),
      pid: runtime.pid,
      port: config.port,
      provider: runtime.provider,
      startedAt: runtime.startedAt,
      webhookConfigured: Boolean(config.webhookUrl),
    },
    "baileys_gateway_listening",
  );
});
