# Instalar as bibliotecas

```bash
pip install customtkinter matplotlib pygame opencv-python numpy PyMuPDF
```

# Gerar Executável

```bash
python -m PyInstaller --onefile --noconsole --icon=riggy-logo.ico main.py
```

# Após Gerar Executável, cole os arquivos mp3 de alerta na pasta dist

# O executável estará lá -> /dist/main.exe
