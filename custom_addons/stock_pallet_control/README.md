# Control de tarimas (stock_pallet_control)

Módulo para **Odoo 18 Community** que controla tarimas con etiqueta de código de barras:
entrada, salida, cambio de ubicación, propietario de la mercancía y mapa de espacios libres/ocupados.

## Cómo funciona

- **Cada tarima es un paquete de Odoo** (`stock.quant.package`, tipo "Tarima").
- **La etiqueta solo lleva el código del paquete** (Code128, ej. `PACK0000020`). Producto, cantidad,
  lote, propietario y ubicación los guarda Odoo; al escanear, Odoo los consulta.
- **Cada espacio de rack** es una ubicación interna con código de barras (ej. `A-01-1`) y categoría de
  almacenamiento "Tarima (1 por ubicación)". Una regla de ubicación asigna automáticamente el
  primer espacio libre al recibir.
- **Propietario**: se captura al recibir; viaja con la tarima en todos los movimientos, así se
  puede conciliar por dueño (Inventario > Reportes).

## Menú: Inventario > Tarimas

| Opción | Para qué sirve |
|---|---|
| Recibir tarimas | Captura el contenido, propietario y número de tarimas iguales. Crea la recepción validada, asigna espacio e imprime etiquetas 4x6". |
| Escáner | **Salida** (escanea la etiqueta) o **Cambio de ubicación** (escanea tarima y luego etiqueta del espacio destino). Genera el movimiento de inventario. |
| Tarimas | Lista de tarimas con ubicación, propietario y contenido. Botón para reimprimir etiqueta. |
| Mapa de ubicaciones | Espacios libres / ocupados, agrupados por rack. |
| Generar ubicaciones | (Solo responsables de inventario) Crea racks y espacios en bloque, con código de barras. |

## Instalación en local

1. Dependencias de Odoo (`pip install -r requirements.txt`) y PostgreSQL. Para imprimir PDF se
   necesita **wkhtmltopdf**.
2. **Código de barras de la etiqueta**: `reportlab` necesita un backend de imagen.
   - Windows (Python 3.12+): ya viene con `rl-renderPM` en `requirements.txt`.
   - Linux / macOS: `pip install rlPyCairo pycairo`.
   Sin esto, la etiqueta falla con `RenderPMError`.
3. Arranca con `custom_addons` en el addons-path y crea/actualiza la base:

   ```
   python odoo-bin -d tarimas -i stock_pallet_control --addons-path=addons,odoo/addons,custom_addons
   ```
   Para actualizar después de cambios: `-u stock_pallet_control`.
4. Entra a Inventario > Tarimas > **Generar ubicaciones** (primero esto: sin espacios las tarimas
   quedan en WH/Stock). Ejemplo: prefijo `A`, posiciones 1–10, niveles 1–3 → `A-01-1` … `A-10-3`.
5. Marca tus productos como **Rastrear inventario** (almacenables); el asistente rechaza los que no lo son.
6. Recibir tarimas → imprimir etiquetas → pegarlas → Escáner para salidas y movimientos.

## Lector de código de barras

Un lector USB/Bluetooth funciona como teclado: escanea con el cursor fuera de los campos de texto.
Si el cursor está en *Cliente* o *Referencia*, el código se escribe ahí. Sin lector, escribe el
código en "Escribir código" y presiona Enter. Para probar sin lector, usa ese campo.

## Notas

- Las ubicaciones usan peso máximo alto en la categoría (100 000) porque con `0` Odoo bloquea
  tarimas con peso. Ajusta en Inventario > Configuración > Categorías de almacenamiento.
- Una tarima con mercancía de varios propietarios no se puede mover; sepárala antes.
- Las salidas/movimientos se agrupan en un documento por almacén y propietario.
- Usuarios internos reciben los permisos de ubicaciones múltiples, paquetes y propietario
  (`security/pallet_security.xml`).
- La etiqueta del espacio de rack usa el reporte estándar de Odoo (Inventario > Configuración >
  Ubicaciones > Imprimir).
- Odoo.sh Enterprise: el módulo depende solo de `stock` y `barcodes`, por lo que también instala allí;
  en Enterprise puedes usar además la app Código de barras nativa sobre los mismos paquetes.

## Pruebas

```
python odoo-bin -d prueba -i stock_pallet_control --test-enable --test-tags /stock_pallet_control --stop-after-init
```
17 pruebas: recepción, asignación de espacios, mapa, salida, movimiento, propietarios, etiqueta, permisos.
