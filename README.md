# FORM19 · captura automática v3 (Render + GitHub)

Este proyecto lee lecturas decimales desde una cámara y escribe **solo E40:K42** del FORM19 XLSM. Conserva los componentes VBA.

## Publicación
1. Subir el contenido de esta carpeta a un repositorio **privado** de GitHub. No subir el formulario de clientes.
2. En Render: New > Web Service > conectar repositorio > Environment: **Docker**. `render.yaml` contiene la configuración de ejemplo.
3. Configurar `APP_PASSWORD` (por solicitud inicial: `admin`; se recomienda una clave más fuerte para datos reales). `SECRET_KEY` debe ser aleatoria y privada.
4. Abrir la URL HTTPS publicada. Subir el archivo .xlsm desde la aplicación, activar cámara, encuadrar *solo la pantalla con dígitos* dentro del recuadro verde. Ajustar tamaño y posición vertical.
5. Marcar captura automática. El sistema espera 2 lecturas iguales consecutivas para evitar errores OCR, guarda la lectura detectada y selecciona la siguiente celda libre.
6. Si dos mediciones consecutivas presentan exactamente el mismo número, pulsar **Nueva medición** antes de registrar la segunda.
7. Descargar el XLSM actualizado y el CSV de trazabilidad después de la sesión. El almacenamiento del servicio Render es temporal.

## Mejoras de esta versión
- OCR de LCD con inversión, contraste, umbrales y distintos modos Tesseract. Rechazo de números sueltos y resultados OCR contradictorios.
- Área de lectura ajustable tanto en tamaño como posición vertical.
- Indicador de resultado OCR bruto para facilitar ajuste.
- Confirmación OCR con dos fotogramas consecutivos, escritura persistida y avance inmediato a la siguiente celda disponible.
- Guardado manual también avanza a la siguiente celda.

## Limitaciones para uso metrológico
El OCR puede confundir 0/8, 1/7 o perder separador decimal según brillo, reflejo, enfoque y modelo del equipo. Se requiere validar con **fotografías reales de la pantalla del alcoholímetro**, verificar el Excel generado y establecer un control de revisión antes de utilizar los datos en certificados. Dos imágenes consecutivas no garantizan reconocimiento correcto.

## Seguridad
`admin` es una contraseña débil y está aquí por la solicitud expresa del usuario. No debe usarse para proteger datos confidenciales en producción.
