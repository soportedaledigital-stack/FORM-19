# DALEDIGITAL FORM19 · Captura automática V4

## Qué cambia

- El archivo `data/FORM19_PLANTILLA.xlsm` **ya viene incorporado**. No hay que cargar ningún Excel.
- Se toma como base el archivo FORM19 facilitado; **únicamente se han vaciado E40:K42** de la hoja `REGISTRO DE DATOS` para que las mediciones anteriores no se mezclen con las nuevas. Se conservan fórmulas, formato y macros VBA.
- Al iniciar sesión se genera una copia de trabajo privada en el almacenamiento temporal de Render.
- Pulse **Iniciar captura automática**. La cámara examina los dígitos, guarda el valor cuando el OCR coincide en dos análisis consecutivos y avanza a la siguiente celda vacía. No hay botones de confirmar ni siguiente lectura.
- Se escribe E40, F40...K40, E41...K42. Puede seleccionar inicialmente la fila que desea completar.
- Tras las capturas, descargue el `.xlsm` y opcionalmente el registro CSV.
- El sistema no modifica otras celdas ni sobrescribe lecturas existentes.

## Desplegar con GitHub + Render

1. Cree un repositorio **privado** en GitHub. El XLSM base contiene información de una calibración anterior y no debería publicarse.
2. Suba **todos** los archivos del ZIP, manteniendo la carpeta `data/`.
3. En Render: New → Web Service → conecte el repositorio → Runtime Docker (usa `Dockerfile`).
4. Configure las variables `APP_PASSWORD` (valor actual por defecto: `admin`) y `SECRET_KEY` (cadena aleatoria larga). Si ya existen en Render, prevalecerán sobre los valores del repositorio.
5. Despliegue. Acceda a la URL HTTPS desde el navegador del celular o PC, permita la cámara y comience a capturar.
6. Antes de cerrar sesión o iniciar una nueva serie, **descargue el Excel**, porque el almacenamiento de Render Free no es permanente.

## Limitaciones metrológicas y operativas

- Se usa OCR (Tesseract) para displays digitales; el rendimiento depende de enfoque, reflejos, tamaño del display y conexión de red. No se ha probado aún con fotos reales de su alcoholímetro. La detección *no es instantánea garantizada*.
- Para reducir falsos positivos se exige ver el mismo valor en **dos análisis consecutivos**. Los valores de 0 a 3 g/L se aceptan, sin comparar con el nominal del MRC.
- Si dos ensayos sucesivos muestran **exactamente el mismo número**, el programa requiere que los dígitos desaparezcan del campo visual en medio (por ejemplo, cuando se retira el alcoholímetro o cambia la pantalla). De lo contrario no puede distinguir una lectura nueva de la misma pantalla sostenida y no duplica la captura.
- El programa no reemplaza la verificación del resultado por el operador antes de emitir el certificado; se recomienda revisar el Excel descargado.
- La contraseña `admin` es débil: para uso real establezca otra en Render y mantenga el repositorio privado.
- Los resultados residen en archivo temporal de la instancia, no en una base de datos persistente.

## Archivos

- `app.py`: endpoints de autenticación, OCR y almacenamiento de XLSM sin reconstruir el libro.
- `templates/index.html`: interfaz móvil, captura automática y visualización de 21 celdas.
- `data/FORM19_PLANTILLA.xlsm`: plantilla incluida con lecturas anteriores vaciadas.
- `Dockerfile`, `requirements.txt`, `render.yaml`: despliegue en Render.
