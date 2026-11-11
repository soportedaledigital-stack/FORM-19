# DALEDIGITAL · Captura de alcoholímetros FORM19 en Render

Aplicación web para **GitHub + Render**, accesible desde celular y computador (HTTPS). Reconoce lecturas de alcoholímetros con Tesseract OCR y las escribe únicamente en **E40:K42** de `REGISTRO DE DATOS` del archivo `.xlsm` que el operador carga al iniciar la sesión.

**No suba certificados ni archivos XLSM a GitHub.** El repositorio incluye solo el código. El operador carga su Excel en la aplicación; puede descargar el XLSM modificado y el historial CSV. La aplicación modifica directamente el XML de la hoja dentro del XLSM, por lo que conserva el proyecto VBA y el resto del formato, pero **debe validar el libro abierto en Excel** antes de utilizarlo como registro oficial.

## Publicar mediante GitHub y Render

1. Cree un repositorio **privado** en GitHub, por ejemplo `captura-alcoholimetros-form19`.
2. Suba los archivos del ZIP directamente en la raíz del repositorio (`app.py`, `Dockerfile`, `requirements.txt`, `render.yaml`, carpeta `templates`). **No suba** su FORM19.xlsm.
3. Entre en https://dashboard.render.com/ > **New** > **Web Service**.
4. Conecte su cuenta GitHub y seleccione el repositorio. Elija **Language/Runtime: Docker**, plan según disponibilidad y región.
5. En **Environment**, configure `APP_PASSWORD=admin` (ya preconfigurada para pruebas; cámbiela antes de uso real) y `SECRET_KEY` con una cadena aleatoria larga (si utiliza Blueprint con `render.yaml`, `SECRET_KEY` se puede generar automáticamente; `APP_PASSWORD` se solicitará).
6. Configure **Health Check Path** `/health` si aparece en el formulario; es opcional para funcionar.
7. Cree el servicio y abra la dirección `https://<nombre-de-servicio>.onrender.com` que Render le asigne.
8. En el celular: abra esa URL, inicie sesión, cargue el `.xlsm`, active la cámara y marque «Captura y guardado automáticos». Enfoque el número dentro del recuadro verde; la lectura se registrará y avanzará a la siguiente celda libre automáticamente.
9. Descargue el XLSM después de la sesión y abra el archivo en Excel para comprobar los resultados y macros.

## Consideraciones metrológicas y de seguridad

- Reconocimiento óptico **no es infalible**: el modo manual permite confirmar cada lectura, pero el modo automático escribe sin confirmación. **Revise los resultados antes de emitir un certificado** y valide el sistema para uso metrológico. Rechace imágenes ambiguas.
- Las celdas con lecturas preexistentes no se sobrescriben salvo autorización explícita.
- Datos subidos quedan **temporalmente en el servidor** (ficheros en el almacenamiento efímero de Render) y se eliminan al reiniciar el servicio. Descargue el Excel y el CSV antes de terminar. Sin almacenamiento durable no es un registro electrónico permanente.
- El servicio requiere contraseña, pero **no tiene control de usuarios por rol ni bitácora inmutable**; se recomienda un repositorio privado y no usar información sensible de clientes hasta evaluar confidencialidad, seguridad, backup y acceso.
- La app **no actualiza un Excel que esté abierto en Windows**. En Render se procesa la copia subida; debe descargarla.
- No instala OCR en los dispositivos de los operadores: Docker instala Tesseract en Render.
- La plantilla no se incluye en el proyecto para no publicar datos reales.
- Validar funcionamiento, fórmulas y macros sobre un archivo de pruebas antes de implementación metrológica (ISO/IEC 17025, gestión de datos y registros).

## Acceso inicial

La contraseña de prueba es **admin**. Está configurada como valor predeterminado en `app.py` y en `render.yaml`. Si ya existe una variable `APP_PASSWORD` en un servicio de Render anterior, cambie allí el valor a `admin`, ya que las variables del servicio tienen prioridad. Esta contraseña es débil y no debe utilizarse en producción con datos sensibles.

## Funcionamiento del nuevo modo automático

- El reconocimiento se repite continuamente mientras el modo esté activado y haya cámara y Excel cargados. La velocidad depende de la red y del OCR del servidor (no es captura garantizada en tiempo real).
- Reconoce **cualquier valor de 0 a 3 g/L** con hasta cuatro decimales, no busca el valor nominal 0,30. Ajuste el recuadro central verde para aislar el número y evitar otros números de la pantalla.
- Guarda la primera lectura reconocida de manera no ambigua en la siguiente celda vacía E40:K42. Si el valor permanece idéntico, bloquea nuevas capturas hasta que cambie, desaparezca en dos revisiones, o se pulse «Nueva medición». Esto evita llenar siete celdas con una lectura estática.
- Las celdas ya ocupadas nunca se reemplazan automáticamente. Antes de confiar en este modo en un laboratorio, compruebe con un conjunto de valores de prueba y compare contra lectura visual.
- La aplicación **no puede detectar por sí sola cuándo el alcoholímetro inició un nuevo ensayo si el resultado sigue mostrando exactamente el mismo número**; use «Nueva medición» en ese caso.
