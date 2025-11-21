// whatsapp-service/index.js
require("dotenv").config();

const express = require("express");
const cors = require("cors");

const app = express();
app.use(cors());
app.use(express.json());

// Healthcheck simples
app.get("/health", (req, res) => {
  return res.json({ status: "ok", service: "whatsapp-service" });
});

// Endpoint que o Django vai chamar
app.post("/api/send-message", (req, res) => {
  const { phone, message } = req.body || {};

  if (!phone || !message) {
    return res.status(400).json({
      error: "Campos 'phone' e 'message' são obrigatórios."
    });
  }

  // Aqui, por enquanto, só logamos.
  // Depois você pluga wppconnect/baileys/etc.
  console.log("=== WHATSAPP STUB ===");
  console.log("Para:", phone);
  console.log("Mensagem:", message);
  console.log("======================");

  return res.json({ ok: true });
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => {
  console.log(`WhatsApp service rodando em http://localhost:${PORT}`);
});
