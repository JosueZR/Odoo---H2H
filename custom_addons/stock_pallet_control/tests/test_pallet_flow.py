# -*- coding: utf-8 -*-
from ast import literal_eval

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPalletFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Almacén propio de las pruebas (Odoo.sh corre las pruebas de staging sobre una copia de producción).
        cls.warehouse = cls.env['stock.warehouse'].create({'name': 'Pruebas tarimas', 'code': 'TPR1'})
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        # Cliente dueño de la mercancía que GICONSA guarda (no es compra ni venta).
        cls.owner = cls.env['res.partner'].create({'name': 'Cliente Dueño SA', 'is_company': True})
        cls.other_owner = cls.env['res.partner'].create({'name': 'Otro Dueño SA', 'is_company': True})
        cls.product = cls.env['product.product'].create({
            'name': 'Caja congelada', 'type': 'consu', 'is_storable': True})
        cls.product_b = cls.env['product.product'].create({
            'name': 'Bolsa congelada', 'type': 'consu', 'is_storable': True})
        cls.product_lot = cls.env['product.product'].create({
            'name': 'Producto con lote', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        cls.tarima = cls.env.ref('stock_pallet_control.package_type_tarima')

    # ------------------------------------------------------------------ ayudantes
    def _receipt(self, lines, env=None, owner=None):
        """Recepción manual "Lista" de mercancía de un cliente (remisión, sin orden de compra)."""
        env = env or self.env
        picking_type = self.warehouse.in_type_id
        picking = env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': (owner or self.owner).id,
            'origin': 'REM-042',
            'location_id': self.supplier_location.id,
            'location_dest_id': self.stock_location.id,
            'move_ids': [Command.create({
                'name': product.name,
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': self.supplier_location.id,
                'location_dest_id': self.stock_location.id,
            }) for product, qty in lines],
        })
        picking.action_confirm()
        self.assertEqual(picking.state, 'assigned')
        return picking

    def _split(self, picking, per_pallet=None, lots=None, quantities=None, env=None):
        action = picking.action_open_pallet_split()
        wizard = (env or self.env)['stock.pallet.split'].with_context(action['context']).create({})
        for line in wizard.line_ids:
            product = line.product_id
            if per_pallet and product in per_pallet:
                line.qty_per_pallet = per_pallet[product]
            if lots and product in lots:
                line.lot_name = lots[product]
            if quantities and product in quantities:
                line.quantity = quantities[product]
        wizard.action_split()
        return wizard

    def _validate(self, picking, backorder=None):
        result = picking.button_validate()
        if isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
            wizard = Form(self.env['stock.backorder.confirmation'].with_context(result['context'])).save()
            wizard.process() if backorder else wizard.process_cancel_backorder()
        self.assertEqual(picking.state, 'done')

    def _packages(self, picking):
        return picking.move_line_ids.result_package_id.sorted('pallet_index')

    # ------------------------------------------------------------------ entrada
    def test_split_receipt_into_pallets(self):
        picking = self._receipt([(self.product, 100)])
        wizard = self._split(picking, per_pallet={self.product: 40})
        self.assertEqual(wizard.pallet_count, 3)
        self._validate(picking)
        packages = self._packages(picking)
        self.assertEqual(len(packages), 3)
        self.assertEqual([sum(p.quant_ids.mapped('quantity')) for p in packages], [40, 40, 20])
        self.assertEqual(packages.package_type_id, self.tarima)
        self.assertEqual(packages.mapped('pallet_index'), [1, 2, 3])
        self.assertEqual(set(packages.mapped('pallet_total')), {3})
        self.assertEqual(set(packages.mapped('pallet_origin')), {'REM-042'})
        self.assertEqual(packages.location_id, self.stock_location)
        self.assertEqual(self.product.with_context(warehouse_id=self.warehouse.id).qty_available, 100,
                         'Se ve en el almacén (aunque vale $0)')

    def test_split_through_the_form_view(self):
        """Igual que en pantalla: el formulario solo envía lo que la vista permite guardar."""
        picking = self._receipt([(self.product_lot, 100)])
        action = picking.action_open_pallet_split()
        form = Form(self.env['stock.pallet.split'].with_context(action['context']))
        with form.line_ids.edit(0) as line:
            line.lot_name = 'L-FORM'
            line.qty_per_pallet = 30
        self.assertEqual(form.pallet_count, 4)
        form.save().action_split()
        self._validate(picking)
        packages = self._packages(picking)
        self.assertEqual([sum(p.quant_ids.mapped('quantity')) for p in packages], [30, 30, 30, 10])

    def test_split_receipt_with_two_products_numbers_pallets_in_sequence(self):
        picking = self._receipt([(self.product, 50), (self.product_b, 30)])
        wizard = self._split(picking, per_pallet={self.product: 25, self.product_b: 30})
        self.assertEqual(wizard.pallet_count, 3)
        self._validate(picking)
        packages = self._packages(picking)
        self.assertEqual(packages.mapped('pallet_index'), [1, 2, 3])
        self.assertEqual(packages[2].quant_ids.product_id, self.product_b)

    def test_split_lot_product_requires_lot(self):
        picking = self._receipt([(self.product_lot, 20)])
        with self.assertRaises(UserError):
            self._split(picking, per_pallet={self.product_lot: 10})
        self._split(picking, per_pallet={self.product_lot: 10}, lots={self.product_lot: 'L-2026-11'})
        self._validate(picking)
        packages = self._packages(picking)
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages.quant_ids.lot_id.mapped('name'), ['L-2026-11'])

    def test_partial_receipt_leaves_backorder(self):
        picking = self._receipt([(self.product, 100)])
        self._split(picking, per_pallet={self.product: 30}, quantities={self.product: 60})
        self._validate(picking, backorder=True)
        self.assertEqual(len(self._packages(picking)), 2)
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertEqual(backorder.move_ids.product_uom_qty, 40, 'Lo que no llegó queda pendiente')

    def test_split_only_for_ready_receipts(self):
        picking = self._receipt([(self.product, 10)])
        self._split(picking)
        self._validate(picking)
        with self.assertRaises(UserError):
            picking.action_open_pallet_split()

    def test_print_labels_from_receipt(self):
        picking = self._receipt([(self.product, 20)])
        with self.assertRaises(UserError):
            picking.action_print_pallet_labels()
        self._split(picking, per_pallet={self.product: 10})
        self._validate(picking)
        action = picking.action_print_pallet_labels()
        self.assertEqual(action['report_name'], 'stock_pallet_control.report_pallet_label')
        self.assertEqual(set(action['context']['active_ids']), set(self._packages(picking).ids))

    def test_label_shows_barcode_product_lot_and_company(self):
        picking = self._receipt([(self.product_lot, 5)])
        self._split(picking, lots={self.product_lot: 'L-ETQ'})
        self._validate(picking)
        package = self._packages(picking)
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'stock_pallet_control.report_pallet_label', package.ids)
        html = html.decode()
        for text in (package.name, 'Producto con lote', 'L-ETQ', 'REM-042', self.env.company.name,
                     'Cliente Dueño SA'):
            self.assertIn(text, html)
        self.assertIn('data:image/png;base64', html, 'Debe incluir la imagen del código de barras')

    # ------------------------------------------------------------------ salida y movimientos
    def _pallet(self, qty=40):
        picking = self._receipt([(self.product, qty)])
        self._split(picking)
        self._validate(picking)
        return self._packages(picking)

    def _delivery(self, packages=None, product_qty=None):
        out_type = self.warehouse.out_type_id
        dest = out_type.default_location_dest_id
        vals = {
            'picking_type_id': out_type.id,
            'partner_id': self.owner.id,
            'location_id': self.stock_location.id,
            'location_dest_id': dest.id,
        }
        if packages:
            vals['package_level_ids'] = [Command.create({
                'package_id': p.id, 'location_dest_id': dest.id,
                'company_id': self.warehouse.company_id.id}) for p in packages]
        if product_qty:
            vals['move_ids'] = [Command.create({
                'name': self.product.name, 'product_id': self.product.id, 'product_uom_qty': product_qty,
                'product_uom': self.product.uom_id.id, 'location_id': self.stock_location.id,
                'location_dest_id': dest.id})]
        delivery = self.env['stock.picking'].create(vals)
        delivery.action_confirm()
        delivery.action_assign()
        return delivery

    # ------------------------------------------------------------------ mercancía de clientes ($0)
    def test_client_goods_have_owner_on_every_pallet(self):
        packages = self._pallet(40) | self._pallet(10)
        self.assertEqual(packages.owner_id, self.owner)
        self.assertEqual(packages.quant_ids.owner_id, self.owner)

    def test_client_goods_add_no_inventory_value(self):
        if 'stock.valuation.layer' not in self.env:
            self.skipTest('Valuación (stock_account) no instalada')
        self.product.standard_price = 25.0
        self._pallet(40)
        layers = self.env['stock.valuation.layer'].search([('product_id', '=', self.product.id)])
        self.assertEqual(sum(layers.mapped('value')), 0, 'La mercancía del cliente vale $0')
        self.assertEqual(sum(layers.mapped('quantity')), 0, 'No suma al inventario valuado')

    def test_owner_cannot_be_own_company(self):
        picking = self._receipt([(self.product, 10)], owner=self.env.company.partner_id)
        with self.assertRaises(UserError):
            self._split(picking)

    def test_exit_by_pallet_keeps_owner_and_frees_stock(self):
        """Salida escaneando / eligiendo la tarima del cliente."""
        package = self._pallet(40)
        self.assertTrue(self.warehouse.out_type_id.show_entire_packs)
        delivery = self._delivery(packages=package)
        self.assertEqual(delivery.state, 'assigned')
        self._validate(delivery)
        self.assertEqual(package.location_id.usage, 'customer')
        self.assertEqual(package.owner_id, self.owner)

    def test_delivery_without_pallet_does_not_take_client_goods(self):
        """Una entrega propia (p. ej. de una venta) que pide producto no toma mercancía de clientes."""
        self._pallet(40)
        delivery = self._delivery(product_qty=10)
        self.assertNotEqual(delivery.state, 'assigned')
        self.assertFalse(delivery.move_line_ids)
        # Con mercancía propia sí aparta, y solo de la propia.
        self.env['stock.quant']._update_available_quantity(self.product, self.stock_location, 15)
        delivery.action_assign()
        self.assertEqual(delivery.state, 'assigned')
        self.assertFalse(delivery.move_line_ids.owner_id)

    def test_reconciliation_report_lists_client_pallets(self):
        package = self._pallet(40)
        self._pallet(10)
        other = self._receipt([(self.product, 7)], owner=self.other_owner)
        self._split(other)
        self._validate(other)
        self.env['stock.quant']._update_available_quantity(self.product, self.stock_location, 99)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock_pallet_control.action_pallet_reconciliation')
        quants = self.env['stock.quant'].search(
            literal_eval(action['domain']) + [('location_id', 'child_of', self.stock_location.id)])
        self.assertEqual(sum(quants.filtered(lambda q: q.owner_id == self.owner).mapped('quantity')), 50)
        self.assertEqual(sum(quants.filtered(lambda q: q.owner_id == self.other_owner).mapped('quantity')), 7)
        self.assertTrue(all(q.owner_id for q in quants), 'La mercancía propia no aparece')
        self.assertIn(package, quants.package_id)

    def test_move_pallet_scanning_the_package(self):
        """Interna como en Código de barras: se agrega la tarima (paquete) y se valida."""
        package = self._pallet(40)
        shelf = self.env['stock.location'].create({
            'name': 'Cámara 2', 'location_id': self.stock_location.id, 'usage': 'internal'})
        int_type = self.warehouse.int_type_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': int_type.id,
            'location_id': self.stock_location.id,
            'location_dest_id': shelf.id,
            'package_level_ids': [Command.create({
                'package_id': package.id, 'location_dest_id': shelf.id,
                'company_id': self.warehouse.company_id.id})],
        })
        picking.action_confirm()
        picking.action_assign()
        self._validate(picking)
        self.assertEqual(package.location_id, shelf)
        self.assertEqual(sum(package.quant_ids.mapped('quantity')), 40)

    # ------------------------------------------------------------------ configuración
    def test_entire_packs_on_all_outgoing_and_internal_types(self):
        types = self.env['stock.picking.type'].with_context(active_test=False).search(
            [('code', 'in', ('outgoing', 'internal'))])
        types.write({'show_entire_packs': False})
        active_before = types.mapped('active')
        self.env['stock.picking.type']._pallet_setup_operation_types()
        self.assertTrue(all(types.mapped('show_entire_packs')))
        self.assertEqual(types.mapped('active'), active_before, 'No activa ni desactiva tipos de operación')

    def test_new_warehouse_gets_entire_packs(self):
        warehouse = self.env['stock.warehouse'].create({
            'name': 'Pruebas tarimas 2', 'code': 'TPR2', 'delivery_steps': 'pick_ship'})
        self.assertTrue(warehouse.out_type_id.show_entire_packs)
        self.assertTrue(warehouse.pick_type_id.show_entire_packs)
        self.assertFalse(warehouse.in_type_id.show_entire_packs)

    def test_internal_users_can_use_packages(self):
        user = self.env['res.users'].create({
            'name': 'Operador', 'login': 'operador_tarimas',
            'groups_id': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('stock.group_stock_user').id])],
        })
        self.assertTrue(user.has_group('stock.group_tracking_lot'))
        self.assertTrue(user.has_group('stock.group_tracking_owner'))
        picking = self._receipt([(self.product, 10)], env=self.env(user=user))
        self._split(picking, env=self.env(user=user))
        self._validate(picking)
        self.assertEqual(len(self._packages(picking)), 1)

    def test_old_screens_are_gone(self):
        self.assertFalse(self.env['ir.actions.client'].search(
            [('tag', '=', 'stock_pallet_control.inventory_dashboard')]))
        self.assertFalse(self.env.ref('stock_pallet_control.menu_pallet_receive', raise_if_not_found=False))
