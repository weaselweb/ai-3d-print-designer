FROM python:3.11-slim

# CadQuery/OCP need a few shared libs for headless geometry kernels.
# Font Awesome 6 Free Solid provides the sign icon glyphs (app/signs/icons.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglu1-mesa libxrender1 libxext6 libsm6 \
      fontconfig fonts-dejavu-core curl \
    && mkdir -p /usr/share/fonts/opentype/fontawesome \
    && curl -fsSL -o "/usr/share/fonts/opentype/fontawesome/fa6-solid.otf" \
         "https://raw.githubusercontent.com/pyapp-kit/fonticon-fontawesome6/main/src/fonticon_fa6/fonts/Font%20Awesome%206%20Free-Solid-900.otf" \
    && fc-cache -f \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
