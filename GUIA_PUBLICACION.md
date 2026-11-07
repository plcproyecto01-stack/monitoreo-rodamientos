# Publicar la aplicación en internet (celular + computadora)

Necesitas tres cuentas gratuitas: **Supabase** (base de datos), **GitHub** (guardar el código) y **Streamlit Community Cloud** (publicar la aplicación). Usa el mismo correo en las tres. Tiempo total: unos 30 minutos.

---

## Parte 1. Base de datos en Supabase

1. Entra a https://supabase.com y crea una cuenta con **Start your project**.
2. Pulsa **New project**. Nombre: `rodamientos-espe`. Escribe una contraseña de base de datos (guárdala) y elige la región **East US** o la más cercana. Pulsa **Create new project** y espera 1–2 minutos.
3. En el menú de la izquierda abre **SQL Editor** → **New query**.
4. Abre el archivo `supabase_tablas.sql` de esta carpeta con el Bloc de notas, copia todo, pégalo en Supabase y pulsa **Run**. Debe decir *Success*.
5. Ve a **Project Settings** (engranaje) → **Data API** y copia la **Project URL** (algo como `https://abcd1234.supabase.co`).
6. Ve a **Project Settings** → **API Keys** y copia la **Secret key** (empieza con `sb_secret_`). Si tu proyecto muestra claves antiguas, usa la **service_role**.

> ⚠️ La clave secreta da acceso total a tus datos: **no la publiques ni la subas a GitHub**. Solo va en los *Secrets* de Streamlit (Parte 3).

## Parte 2. Subir el código a GitHub

1. Entra a https://github.com y crea una cuenta.
2. Pulsa **+** (arriba a la derecha) → **New repository**. Nombre: `monitoreo-rodamientos`. Déjalo **Public** y pulsa **Create repository**.
3. En la página del repositorio pulsa **uploading an existing file**.
4. Abre esta carpeta en el Explorador, **selecciona todo su contenido** (incluida la carpeta `.streamlit`, `catalogos` y `datos_prueba`) y arrástralo a la página de GitHub.
5. Espera a que suban todos los archivos y pulsa **Commit changes**.

> El archivo `.gitignore` evita que se suban tus datos locales y el archivo de contraseñas.

## Parte 3. Publicar en Streamlit Community Cloud

1. Entra a https://share.streamlit.io y elige **Continue with GitHub**. Autoriza el acceso.
2. Pulsa **Create app** → **Deploy a public app from GitHub**.
3. Elige el repositorio `monitoreo-rodamientos`, rama `main`, archivo principal `app_rodamientos.py`.
4. En **App URL** escribe un nombre corto, por ejemplo `rodamientos-espe` (quedará `https://rodamientos-espe.streamlit.app`).
5. Abre **Advanced settings**: en *Python version* elige **3.12** y en *Secrets* pega (con tus valores):

   ```toml
   app_password = "una-contraseña-para-el-grupo"
   supabase_url = "https://abcd1234.supabase.co"
   supabase_key = "sb_secret_..."
   ```

6. Pulsa **Deploy**. La primera vez tarda 2–4 minutos en instalar todo.
7. Entra con la contraseña. En la barra lateral debe decir **☁️ Datos en la nube (Supabase)**.

## Parte 4. Instalarla como aplicación

- **Android (Chrome):** abre la dirección → menú **⋮** → **Agregar a la pantalla principal** (o **Instalar app**).
- **iPhone (Safari):** abre la dirección → botón **Compartir** → **Agregar a inicio**.
- **Computadora (Chrome o Edge):** abre la dirección → icono de instalar en la barra de dirección, o menú → **Aplicaciones** → **Instalar este sitio como aplicación**.

Queda un ícono con el logo de Electromecánica que abre la aplicación como si fuera una app.

## Parte 5. Alertas por Telegram

Dentro de la aplicación, en **🔔 Alertas**, están los pasos: crear el bot con **@BotFather**, pegar el token, escribirle al bot, pulsar **Buscar mi chat ID**, activar y **Enviar mensaje de prueba**. Cada integrante puede agregar su chat ID separado por coma.

---

## Notas

- **Si la app «se duerme»:** en el plan gratuito, si nadie la abre durante un tiempo, Streamlit la pone en reposo. Al entrar aparece un botón para despertarla; tarda unos 30 segundos. Los datos no se pierden porque están en Supabase.
- **Actualizar la aplicación:** cuando haya una versión nueva de `app_rodamientos.py`, súbela a GitHub (Add file → Upload files) y Streamlit la actualiza sola en 1–2 minutos.
- **Seguir usándola en la PC sin internet:** `INICIAR.bat` funciona igual que antes, guardando en archivos locales. Para que la versión de la PC use también la nube, copia `.streamlit/secrets.toml.ejemplo` como `.streamlit/secrets.toml` y llénalo con los mismos valores.
- **Recordatorios de mantenimiento:** se envían por Telegram la primera vez que alguien abre la aplicación cada día. El monitoreo automático las 24 horas llegará en la fase 3 (lectura directa del PLC).
