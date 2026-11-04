# Control de tarimas (stock_pallet_control)

Módulo para **Odoo 18** (Community local / Enterprise en Odoo.sh). Se trabaja con los documentos
estándar de Inventario, Compras y Ventas; el módulo solo agrega:

- **"Separar en tarimas"** en la Recepción (la que genera la orden de compra).
- **"Imprimir etiquetas de tarima"**: etiqueta 4x6 con el código de barras del paquete.
- **"Mover paquetes completos"** en Entregas y operaciones internas de todos los almacenes.

Cada tarima es un **paquete** de Odoo (tipo "Tarima"). La etiqueta lleva el código del paquete
(Code128, ej. `PACK0000039`); producto, lote, cantidad y ubicación los guarda Odoo.

## Uso diario

| Paso | Dónde | Cómo |
|---|---|---|
| 1. Entrada | Compras > orden confirmada > **Recepción** | Botón **Separar en tarimas**: lote y *cantidad por tarima* (ej. 100 con 30 por tarima → 4 tarimas: 30, 30, 30, 10). **Crear tarimas** → **Validar**. Si llegó menos, baja la *cantidad recibida*: Odoo ofrece el pendiente (backorder). |
| 2. Etiquetas | La recepción validada | **Imprimir etiquetas de tarima** → pegar una en cada tarima. |
| 3. Salida | Ventas > orden confirmada > **Entrega** | Odoo aparta producto; en la sección *Paquete* se ve la tarima completa. En la app **Código de barras** (Enterprise) se escanea la etiqueta de la tarima que se carga. **Validar**. |
| 4. Movimiento | Inventario > Operaciones > Internas | Agrega la tarima en *Paquete* (o escanéala), destino y **Validar**. |
| Consultar | Inventario > Productos > **Paquetes** | Columnas *Contenido* y *Documento de origen*. |

Con lector USB/Bluetooth en Community: el lector escribe como teclado; escanea dentro del campo *Paquete*.

## Qué cambia al instalar

- Todos los usuarios internos pueden usar **paquetes** (igual que Inventario > Ajustes > Paquetes).
- Se crea el tipo de paquete **Tarima** (código de barras `TARIMA`).
- **Una sola vez** (al instalar o al actualizar desde una versión anterior): se activa "Mover paquetes
  completos" en Entregas e internas de todos los almacenes. No activa ni desactiva tipos de operación.
  Los almacenes que se creen después ya nacen con la opción. Si un responsable la apaga en algún tipo
  de operación, las actualizaciones no la vuelven a prender.

## Notas

- **Qué tarima aparta Odoo en una entrega**: por defecto toma primero lo que entró antes (FIFO), aunque eso
  parta una tarima. Con la app Código de barras el operador escanea la tarima que realmente carga.
  Si se quiere que Odoo prefiera tarimas completas: Inventario > Configuración > Categorías de producto >
  Estrategia de remoción **"Menos paquetes"** (ojo: deja de priorizar el lote más antiguo).
- Productos con **número de serie**: usar "Poner en paquete" nativo; el asistente maneja sin rastreo o por lote.
- La etiqueta imprime el nombre de la compañía de la tarima.

## Instalación

### Local
1. Dependencias (`pip install -r requirements.txt`) y PostgreSQL.
2. PDF: **wkhtmltopdf** debe estar en el PATH, o en `odoo.conf`:
   `bin_path = C:\Program Files\wkhtmltopdf\bin`
3. Código de barras de la etiqueta en Linux/macOS: `pip install rlPyCairo pycairo`
   (Windows ya trae `rl-renderPM`).
4. Actualizar: `python odoo-bin -c odoo.conf -d <base> -u stock_pallet_control`

### Odoo.sh
1. Sube `custom_addons/stock_pallet_control` a la rama de **staging** del repositorio de Odoo.sh.
2. Un **administrador** instala "Control de tarimas: etiquetas" en Aplicaciones (actualizar lista primero).
3. Prueba con una orden de compra y una de venta reales. Si todo está bien, fusiona a producción.

## Pruebas

```
python odoo-bin -c odoo.conf -d prueba -i stock_pallet_control --test-enable --test-tags /stock_pallet_control --stop-after-init
```
14 pruebas: separar recepción en tarimas (también desde el formulario), lotes, recepción parcial,
etiquetas, entrega por producto que toma la tarima completa, movimiento interno, configuración de
tipos de operación (existentes y almacenes nuevos) y permisos. Usan un almacén propio, así que pasan
también sobre una copia de producción (staging de Odoo.sh).
