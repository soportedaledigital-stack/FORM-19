# DALEDIGITAL DISPOSITIVOS · FORM19 V5

Corrección del proyecto FORM-19-main suministrado el 13 de noviembre de 2026.

## Actualizar el servicio existente

1. Descargue los registros de la versión anterior que todavía estén disponibles. La actualización de un servicio con almacenamiento temporal puede perder esos archivos.
2. Descomprima este paquete. En el repositorio GitHub que ya utiliza el servicio, reemplace el contenido del proyecto por **el contenido de esta carpeta**. No suba únicamente el ZIP ni anide otra carpeta dentro del proyecto existente.
3. Compruebe que en el mismo nivel estén `Dockerfile`, `app.py`, `form19_core.py`, `requirements.txt` y las carpetas `templates`, `static` y `data`.
4. Confirme que existe `data/FORM19_PLANTILLA.xlsm`. El archivo debe conservar ese nombre y esa ruta.
5. Guarde los cambios en la rama que usa Render. En el servicio seleccione **Manual Deploy → Deploy latest commit**, si no se ha iniciado automáticamente el despliegue. El servicio debe utilizar Docker y este Dockerfile.
6. Mantenga las variables existentes `APP_PASSWORD` y `SECRET_KEY`. Para un servicio nuevo, configure una contraseña robusta y una clave secreta aleatoria. El código conserva `admin` únicamente como valor de compatibilidad cuando no se define APP_PASSWORD; no es adecuado para uso real.
7. Abra la dirección HTTPS del servicio, recargue la página e inicie sesión. La cabecera debe mostrar **V5 · 2026-11-13**. Si sigue viendo V4, revise la rama desplegada y vuelva a cargar la página.
8. Pulse **Iniciar captura automática**, autorice la cámara y encuadre solo el número con su separador decimal.

No es necesario crear otro servicio ni cambiar el archivo Excel base. Sí es necesario subir todos los archivos nuevos; cambiar solo Dockerfile corrige la inclusión de la plantilla, pero no actualiza la cámara ni la interfaz.

Documentación de referencia:
- Despliegues: https://render.com/docs/deploys
- Instrucción COPY: https://docs.docker.com/reference/dockerfile/#copy
- Permiso de cámara y HTTPS: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- Tiempo límite de OCR: https://github.com/madmaze/pytesseract

## Fallos encontrados en la versión recibida

**Plantilla ausente del despliegue.** El Dockerfile original copiaba `app.py` y `templates`, pero no la carpeta `data`. Por ello, el archivo `FORM19_PLANTILLA.xlsm` presente en el ZIP no entraba en la imagen Docker. El inicio de sesión, el guardado y la descarga dependían de ese archivo.

**Estado de preparación engañoso.** `/api/status` ocultaba las excepciones y devolvía una respuesta HTTP 200 con `uploaded=False`. La interfaz no comprobaba ese campo y podía indicar «Plantilla lista» aunque el archivo faltara.

**Reconocimiento lento y sin límite de ejecución por proceso.** La ruta automática ejecutaba 5 variantes de imagen por 3 configuraciones OCR: 15 invocaciones por fotografía. Además, necesitaba dos análisis concordantes antes de guardar. No se ha medido la velocidad del servicio real de Render; la revisión del código sí confirma esa carga de trabajo.

**No se conservaba una fotografía de respaldo.** Las imágenes se enviaban para reconocimiento, pero no se asociaba una fotografía persistida a cada lectura guardada.

**Mensajes poco útiles.** La interfaz intentaba interpretar cualquier respuesta como JSON y el enlace de descarga no mostraba un error dentro de la aplicación.

## Cambios de V5

- Docker incluye `data`, `static` y el módulo de funciones. La construcción comprueba la estructura de la plantilla.
- El servicio no informa que está saludable cuando faltan la plantilla o Tesseract.
- El inicio de sesión no se confirma si no se puede preparar el Excel. Los errores de estado y descarga se muestran en español.
- Se usa una sola invocación de Tesseract por imagen, con tres variantes en una composición y un tiempo límite. Se mantienen los controles de concordancia; esto no garantiza la exactitud del reconocimiento sobre un equipo real.
- La interfaz espera a que la cámara entregue imágenes y explica problemas de permisos, HTTPS o cámara ocupada.
- El recuadro de lectura tiene ancho, alto y posición ajustables y coincide con la imagen enviada.
- Cada lectura guardada conserva el recorte JPEG utilizado para su reconocimiento. El servidor vincula imagen, valor, celda e identificador para evitar asociar una foto diferente.
- Se muestra la última foto guardada y se puede descargar un ZIP con Excel, fotografías, historial y manifiesto con hashes SHA-256.
- La misma pantalla sostenida no se registra repetidamente. Para dos mediciones iguales debe desaparecer el número durante al menos tres análisis sin texto. Una lectura ambigua no rearma por sí sola una medición repetida.
- Las solicitudes de guardado repetidas con el mismo identificador son idempotentes. No se sobrescriben celdas ocupadas.
- Una copia temporal desaparecida no se sustituye silenciosamente por un Excel vacío al descargar.
- Se detiene la cámara al descargar, reiniciar, salir o dejar la página en segundo plano. Se espera un guardado ya iniciado antes de ejecutar acciones destructivas.

## Funcionamiento conservado

La plantilla incorporada es **idéntica byte por byte a la del ZIP recibido**. No se reconstruye el libro ni se eliminan macros. Los valores nuevos se escriben únicamente en `REGISTRO DE DATOS!E40:K42`, de izquierda a derecha desde la fila elegida. Los demás miembros del XLSM se conservan. Las fotos se descargan por separado y no alteran el diseño del formato.

Las referencias de la interfaz siguen siendo las del proyecto recibido: 0,2982; 0,7915 y 1,4878 g/L. No se cambia un resultado para aproximarlo a la referencia. Solo se aceptan valores entre 0 y 3 g/L. Un separador decimal no reconocido no se inventa; un número como `300` no se convierte automáticamente en `0,300`.

Se necesita revisión del operador antes de utilizar los resultados en un certificado. La plantilla original conserva información de una calibración anterior fuera del intervalo de lecturas: revise y actualice los datos correspondientes antes de emitir documentos. Mantenga privado el repositorio.

## Comprobación después de desplegar

1. Sin usar la cámara, pruebe **Descargar FORM19 (.xlsm)**. Debe descargar un Excel, no una página de error.
2. Inicie la cámara y encuadre una lectura conocida. Espere la concordancia de dos imágenes. Deben aparecer valor, celda y fotografía guardados.
3. Deje el mismo número visible: no debe llenar más celdas por mantener la pantalla quieta.
4. Retire el display hasta que el mensaje indique que está listo para otra medición; vuelva a mostrarlo para probar un resultado idéntico nuevo.
5. Descargue el XLSM y compruebe que el valor está en la celda indicada. Descargue también el paquete con fotos y revise su correspondencia.

Use una sola pestaña para capturar en una sesión. La pérdida de enfoque, reflejos, fuentes de siete segmentos y decimales muy pequeños pueden requerir ajustar el encuadre. No se ha validado el reconocimiento con imágenes reales del alcoholímetro del usuario.

## Almacenamiento y seguridad

Los archivos siguen siendo temporales. No se añadió una base de datos ni almacenamiento permanente. Descargue Excel y evidencias antes de salir, iniciar otra serie o actualizar/reiniciar el servicio. Una nueva autenticación sin una sesión de trabajo recuperable comienza una serie nueva; no recupera archivos que el servidor haya eliminado.

No comparta las variables de entorno ni incluya contraseñas reales en el repositorio. En producción se debe mantener un único proceso worker porque las transacciones de archivo utilizan un bloqueo dentro de ese proceso; el Dockerfile suministrado ya lo configura así.

## Pruebas

Consulte `VERIFICACION.txt` para el alcance real de las comprobaciones realizadas. Los comandos de pruebas unitarias son:

```sh
python -m unittest discover -s tests -p 'test_core.py' -v
node tests/test_capture_state.js
```

`tests/browser_smoke.py` es una comprobación adicional con Playwright/Chromium y cámara/API simuladas. Playwright es una dependencia de prueba opcional; no se necesita para ejecutar la aplicación en Render.
