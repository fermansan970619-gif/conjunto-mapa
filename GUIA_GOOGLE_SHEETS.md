# Guía: conectar el mapa a Google Sheets (paso a paso)

**Resultado final:** la gente llena un formulario → la respuesta cae en una hoja de Google → el mapa la muestra solo, en unos 20–40 segundos, sin recargar.

```
Vecino → Google Form → Hoja de Google ← (cada ~20 s) ← Servidor Python → Mapa en el navegador
```

Nadie edita la hoja directamente, y la clave de Google vive solo en el servidor.

Los nombres de los menús de Google pueden cambiar un poco con el tiempo; la idea de cada paso se mantiene.

---

## Parte 1. Crear el formulario para agregar sitios

1. Entre a https://forms.google.com → **Formulario en blanco**. Título: «Agregar un sitio de interés».
2. **Configuración → Respuestas:** deje **desactivado** «Recopilar direcciones de correo electrónico» y «Limitar a 1 respuesta». (La hoja será de lectura pública: no recolecte datos personales de quien responde).
3. Cree estas preguntas (los títulos importan: el portal los reconoce por su nombre):

| Pregunta | Tipo | ¿Obligatoria? |
|---|---|---|
| **Nombre del sitio** | Respuesta corta | Sí |
| **Categoría** | Desplegable: Parqueadero, Centro comercial, Salud, Supermercado, Transporte, Educación, Parque, Restaurante, Banco, Deporte, Otros | Sí |
| **Coordenadas** | Respuesta corta | Sí |
| **Dirección** | Respuesta corta | No |
| **Descripción** | Párrafo | No |
| **Horario** | Respuesta corta | No |
| **Teléfono** | Respuesta corta | No |
| **Página web** | Respuesta corta | No |

4. En la pregunta **Coordenadas**, abra los tres puntos ⋮ → **Descripción** y escriba:
   > En Google Maps, haga clic derecho (en el celular, mantenga presionado) sobre el lugar y toque los números que aparecen arriba (ejemplo: 4.6483, -74.1429) para copiarlos. Péguelos aquí.
5. Aún en **Coordenadas**, ⋮ → **Validación de respuestas** → **Expresión regular** → **Coincide con**, y pegue:
   ```
   ^\s*-?\d{1,2}[.,]\d+\s*[,;]\s*-?\d{1,3}[.,]\d+\s*$
   ```
   Texto de error: «Pegue las coordenadas tal como las copia Google Maps, por ejemplo 4.6483, -74.1429». Así nadie envía «cerca del parque».
6. Pulse **Enviar → icono de enlace** y copie el enlace (empieza por `https://forms.gle/…`). Lo usará en `ENLACE_AGREGAR_SITIO`.

## Parte 2. Vincular el formulario con una hoja y prepararla

1. En el formulario: pestaña **Respuestas → icono verde «Vincular con Hojas de cálculo» → Crear una hoja de cálculo nueva**. Se abre la hoja; la pestaña se llama «Respuestas de formulario 1».
2. En esa hoja, en la **primera celda vacía de la fila 1, a la derecha de la última columna**, escriba el encabezado **Aprobado**. No cambie las demás columnas ni agregue columnas en medio.
3. **Compartir** (botón verde arriba a la derecha) → **Acceso general** → **Cualquier persona con el enlace** → rol **Lector**. Esto es necesario para que la clave de API pueda leerla.
4. Copie el **ID de la hoja**: es la parte larga de la URL entre `/d/` y `/edit`:
   `https://docs.google.com/spreadsheets/d/`**`1AbC…xyz`**`/edit`
   (También puede pegar la URL completa).
https://docs.google.com/spreadsheets/d/1cqmq-KoYBFtUp0RTKCfoFq0xZHclPrv48xUF0OtmK-s/edit?usp=sharing
> **Importante:** como la hoja es de lectura pública, cualquiera con el enlace puede verla. Por eso el formulario no debe pedir datos personales.

## Parte 3. Habilitar la API y crear la clave (Google Cloud)

No debería pedirle tarjeta de crédito ni facturación para esto; si Google se la pide, deténgase y revise.

1. Entre a https://console.cloud.google.com con la misma cuenta de Google.
2. Arriba, junto al logo, abra el selector de proyectos → **Proyecto nuevo** → nombre «portal-mapa» → **Crear**. Verifique que quede seleccionado.
3. Menú ☰ → **APIs y servicios → Biblioteca**. Busque **Google Sheets API** → **Habilitar**.
4. Menú ☰ → **APIs y servicios → Credenciales** → **+ Crear credenciales → Clave de API**. Copie la clave que aparece.
5. Pulse **Editar clave de API** (o el nombre de la clave) y configure:
   - **Restricciones de API → Restringir clave → marque solo «Google Sheets API»** → **Guardar**.
   - **Restricciones de la aplicación:** déjela en «Ninguna» para empezar. Cuando publique el sitio con una IP fija, puede restringirla a «Direcciones IP» con la IP de su servidor.
6. Espere 1–2 minutos a que Google propague la clave.

> **La clave es secreta.** No la escriba en `config.py`, no la suba a GitHub ni la comparta por chat. Si se filtra: en Credenciales, elimínela y cree otra.

## Parte 4. Conectar el portal

Defina estas variables de entorno antes de iniciar la aplicación:

**Windows (PowerShell), solo para esta sesión:**
```powershell
$env:GOOGLE_SHEET_ID = "1AbC...xyz"
$env:GOOGLE_API_KEY = "AIza..."
$env:ENLACE_AGREGAR_SITIO = "https://forms.gle/..."
python app.py
```
Para que queden permanentes en Windows: `setx GOOGLE_API_KEY "AIza..."` (y lo mismo con las otras) y abra una terminal nueva.

**Linux / Mac:**
```bash
export GOOGLE_SHEET_ID="1AbC...xyz"
export GOOGLE_API_KEY="AIza..."
export ENLACE_AGREGAR_SITIO="https://forms.gle/..."
python app.py
```

**En un servicio de alojamiento:** agréguelas en su panel de «Environment variables / Variables de entorno». Nunca dentro del código.

Si su pestaña no es la primera, defina también `GOOGLE_SHEET_PESTANA` con el nombre exacto.

## Parte 5. Probar

1. Abra http://127.0.0.1:5000/estado. Debe decir **Fuente: Google Sheets · al día**. Si dice «con problemas», el mensaje en rojo indica la causa (ver tabla al final).
2. Abra el mapa en una pestaña y deje la página abierta.
3. En otra pestaña llene el formulario con un sitio de prueba (use coordenadas cercanas al conjunto).
4. En 20–40 segundos debe aparecer en el mapa con el aviso «➕ Nuevo sitio». Si no, mire `/estado`.
5. Borre la fila de prueba en la hoja cuando termine.

---

## Moderación (decide qué tan «abierto» es)

En `config.py`:

| `REQUIERE_APROBACION` | Qué pasa |
|---|---|
| `False` (por defecto) | Todo registro válido se publica **al instante**. Para ocultar uno, escriba **NO** en su celda «Aprobado». |
| `True` | Solo se publican las filas con **SÍ** en «Aprobado». Usted revisa y aprueba. Recomendado cuando el formulario se comparta ampliamente. |

Aunque no haya moderación, el portal descarta por sí solo: filas sin coordenadas válidas, sitios a más de 15 km del conjunto (`MAX_DISTANCIA_SITIO_KM`), textos demasiado largos y enlaces que no sean http(s).

## ¿Y si prefiero que la gente edite la hoja directamente?

Se puede (compartir como **Editor**), pero **no lo recomiendo**: cualquiera con el enlace podría borrar filas, cambiar datos de otros o aprobarse a sí mismo. Si aun así lo hace, comparta el enlace de la hoja en `ENLACE_AGREGAR_SITIO`, ponga `REQUIERE_APROBACION = False` y revise el historial de versiones de Google (**Archivo → Historial de versiones**) si hay vandalismo.

## Cuántas consultas hace a Google

El servidor consulta la hoja como máximo **cada 20 segundos**, sin importar cuántas personas tengan el mapa abierto: unas 3 por minuto, muy por debajo de la cuota gratuita de Google (300 por minuto por proyecto). Si Google falla, el mapa sigue mostrando la última lectura buena (también tras reiniciar el servidor, gracias a `data/sitios_copia.json`).

## Errores frecuentes (los muestra `/estado`)

| Mensaje | Qué hacer |
|---|---|
| La hoja no es pública… | Parte 2, paso 3: «Cualquier persona con el enlace → Lector». |
| La clave de API no es válida | Revise `GOOGLE_API_KEY` (sin espacios ni comillas de más). |
| La API de Google Sheets no está habilitada… | Parte 3, paso 3, en el **mismo proyecto** donde creó la clave. |
| No se encontró la hoja | Revise `GOOGLE_SHEET_ID`. |
| No se encontró la pestaña indicada | `GOOGLE_SHEET_PESTANA` debe coincidir exactamente con el nombre. |
| La clave tiene restricciones de aplicación… | En la clave, «Restricciones de la aplicación» → «Ninguna» o su IP real. |
| Un registro no aparece | `/estado` cuenta cuántas filas se descartaron y por qué (coordenadas, lejanía, oculta o sin aprobar). |
| Las coordenadas se descartan | La columna «Coordenadas» debe ser **texto** como `4.6483, -74.1429`. Si prefiere columnas separadas de latitud y longitud, en hojas con formato regional español Sheets puede convertir `4.6483` en `46483`: formatee esas columnas como **Texto sin formato**. |
| Enlaces cortos de Google Maps | Los enlaces `maps.app.goo.gl/…` no se pueden leer; pida las coordenadas o el enlace largo. |
