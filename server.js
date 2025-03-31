const express = require('express');
const axios = require('axios');

// Initialisiere Express und erstelle eine Route
const app = express();
const port = 3000;

// API-Route, die für die Anfrage zuständig ist
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;
  const numberPlateText = req.query.numberPlateText; // Das Kennzeichen, das du prüfen möchtest

  console.log(`Anfrage an API mit RegionCode: ${regionCode}`);
  const url = `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`;
  console.log(`Verwendete URL: ${url}`);

  try {
    // Rufe die API mit dem RegionCode ab, um die ServiceId zu erhalten
    const response = await axios.get(url);
    const registrationOfficeServiceId = response.data.registrationOfficeServices[0].registrationOfficeServiceId;

    console.log(`Gefundene registrationOfficeServiceId: ${registrationOfficeServiceId}`);

    // Erstelle den Payload für die Verfügbarkeitsprüfung des Kennzeichens
    const availabilityPayload = {
      numberPlateText: numberPlateText,
      registrationOfficeServiceId: registrationOfficeServiceId,
      vehicleType: "CAR",
      licensePlateType: "REGULAR",
      secondLineLength: null,
      editableLength: 8,
      startMonth: null,
      endMonth: null
    };

    console.log(`Anfrage zur Verfügbarkeit des Kennzeichens: `, availabilityPayload);

    // Verfügbarkeit des Kennzeichens prüfen (hier müsstest du die genaue API-URL für Verfügbarkeit nutzen)
    const availabilityUrl = `https://wunschkennzeichen.zulassung.de/api/availability`;
    const availabilityResponse = await axios.post(availabilityUrl, availabilityPayload);

    res.json(availabilityResponse.data); // Antwort an den Client zurücksenden
  } catch (error) {
    console.error('Fehler beim Abruf:', error.response ? error.response.data : error.message);
    res.status(500).json({ error: 'Fehler beim Abruf der Daten' });
  }
});

// Starte den Server
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
