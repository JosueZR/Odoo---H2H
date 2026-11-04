# Control de tarimas (stock_pallet_control)

Módulo para **Odoo 18** (Community local / Enterprise en Odoo.sh) para la **mercancía de clientes**
que GICONSA guarda o controla: no es compra ni venta, **no suma al valor del inventario** y se
**concilia** contra el reporte de existencias de la bodega (Frialsa, Americold, etc.).

Todo se hace con documentos estándar de Inventario. La pieza clave es nativa de Odoo:
el **Propietario** (consigna). La mercancía con propietario se ve en el almacén, pero Odoo no la
valúa (no crea capas de valuación, vale $0).

El módulo agrega:
- **"Separar en tarimas"** en la Recepción: pide el propietario y crea un paquete (tarima) por tarima.
- **"Imprimir etiquetas de tarima"**: etiqueta 4x6 con código de barras, propietario, lote y referencia.
- **Inventario > Reportes > Conciliación por propietario**: existencias de clientes por cliente,
  ubicación y tarima; se exporta a Excel.
- **Protección**: una entrega que no indica tarima ni propietario (p. ej. de una venta de GICONSA)
  no aparta mercancía de clientes.
- **"Mover paquetes completos"** en Entregas e internas, para sacar o mover la tarima entera.

## Uso diario

| Paso | Dónde | Cómo |
|---|---|---|
| 1. Entrada | Inventario > Operaciones > **Recepciones** > Nuevo | *Recibir de*: el cliente. Producto y cantidad. *Documento origen*: remisión. **Marcar por hacer**. |
| 2. Tarimas | La misma recepción | **Separar en tarimas**: propietario (se propone el cliente), lote y *cantidad por tarima*. **Crear tarimas** → **Validar**. |
| 3. Etiquetas | La recepción validada | **Imprimir etiquetas de tarima** → pegar una en cada tarima. |
| 4. Salida | Inventario > Operaciones > **Entregas** > Nuevo | En la sección *Paquete* agrega la tarima (escribe o escanea `PACK…`). En la app **Código de barras**: escanear la tarima. **Validar**. |
| 5. Conciliar | Inventario > Reportes > **Conciliación por propietario** | Filtra por cliente o ubicación; seleccionar todo > **Exportar** a Excel y comparar contra el reporte de la bodega. |
| Consultar | Inventario > Productos > **Paquetes** | Propietario, contenido y documento de origen de cada tarima. |

## Reglas importantes

- **Siempre con propietario.** El asistente no deja separar en tarimas sin propietario, ni con una
  compañía propia como propietario (eso sí sumaría valor).
- **Salidas de clientes por tarima.** Para sacar mercancía de un cliente se indica la tarima.
  Una entrega que solo pide producto (como las de ventas) toma únicamente mercancía propia.
- **Existencias en pantalla.** La cantidad "a la mano" de un producto incluye la del cliente
  (es física). El valor y lo que una venta puede apartar, no.

## Qué cambia al instalar

- Todos los usuarios internos ven **Paquetes** y **Propietario** (igual que activarlos en Ajustes de Inventario).
- Se crea el tipo de paquete **Tarima** (código de barras `TARIMA`).
- **Una sola vez**: "Mover paquetes completos" en Entregas e internas de todos los almacenes
  (y en los que se creen después). No activa ni desactiva tipos de operación.
- Al apartar mercancía sin tarima ni propietario, Odoo ignora la de clientes (ver Protección).

## Instalación

### Local
1. Dependencias (`pip install -r requirements.txt`) y PostgreSQL.
2. PDF: **wkhtmltopdf** en el PATH, o en `odoo.conf`: `bin_path = C:\Program Files\wkhtmltopdf\bin`
3. Actualizar: `python odoo-bin -c odoo.conf -d <base> -u stock_pallet_control`

### Odoo.sh
1. Sube `custom_addons/stock_pallet_control` a la rama de **staging**.
2. Un **administrador** instala "Control de tarimas: etiquetas" en Aplicaciones.
3. Prueba: recepción de un cliente → tarimas → etiquetas → entrega por tarima → conciliación.
   Revisa en Contabilidad que la recepción del cliente no generó asiento ni valor.

## Pruebas

```
python odoo-bin -c odoo.conf -d prueba -i stock_pallet_control --test-enable --test-tags /stock_pallet_control --stop-after-init
```
19 pruebas: tarimas desde la recepción (también desde el formulario), lotes, parcial, propietario
obligatorio, **valor $0** (si está instalada la valuación), salida por tarima, protección de
mercancía de clientes, conciliación, etiqueta, configuración y permisos. Usan un almacén propio,
así que pasan también sobre una copia de producción (staging de Odoo.sh).
