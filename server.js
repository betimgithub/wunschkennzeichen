const express = require("express");
const axios = require("axios");

const app = express();
const PORT = process.env.PORT || 3000;

// Bright Data Proxy Info
const proxyHost = "brd.superproxy.io";
const proxyPort = 33335;
const proxyUser = "brd-customer-hl_46ab8084-zone-datacenter_proxy1";
const proxyPass = "1q735kkv57ub";

app.get("/api/service", async (req, res) => {
  const { regionCode } = req.query;

  try {
    const response = await axios.get(
      `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`,
      {
        proxy: {
          host: proxyHost,
          port: proxyPort,
          auth: {
            username: proxyUser,
            password: proxyPass,
          },
        },
        headers: {
          "User-Agent": "Mozilla/5.0",
          Accept: "*/*"
        }
      }
    );

    res.json(response.data);
  } catch (error) {
    console.error("Fehler beim Abruf:", error.message);
    res.status(500).json({ error: "Fehler beim Abruf der Zulassungsstelle" });
  }
});

app.listen(PORT, () => {
  console.log(`Server läuft auf Port ${PORT}`);
});