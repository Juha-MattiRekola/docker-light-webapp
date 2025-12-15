FROM python:3.12-alpine

WORKDIR /app

# Asenna riippuvuudet
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]

# Virallinen Python Docker image Alpine Linux -pohjaisena. Käytetään Python 3.12 versiota.
# Työkansio määritellään olemaan /app
# Kopioidaan riippuvuustiedosto "requirements.txt" työkansioon.
# Riippuvuudet "requirements.txt"-tiedostosta asennetaan pip:llä ilman välimuistia. Rekursiivinen asennus on tarpeen, koska sovellus käyttää useita ulkoisia kirjastoja.
# Lopuksi kopioidaan pääsovellustiedosto app.py työkansioon. Se sijaitsee samassa kansiossa kuin Dockerfile.
# Kontti ilmoittaa avoimen portin 5000, jota sovellus käyttää.
# Kontti käynnistää Python-sovelluksen suorittamalla komennot "python" ja  "app.py".