# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPalletFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.owner = cls.env['res.partner'].create({'name': 'Cliente Dueño SA'})
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente Final SA'})
        cls.product = cls.env['product.product'].create({
            'name': 'Caja de prueba', 'type': 'consu', 'is_storable': True, 'weight': 12.5})
        cls.product_b = cls.env['product.product'].create({
            'name': 'Botella de prueba', 'type': 'consu', 'is_storable': True})
        cls.product_lot = cls.env['product.product'].create({
            'name': 'Producto con lote', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        # Dos espacios libres: T-01-1 y T-02-1
        cls.env['stock.pallet.location.generator'].create({
            'prefix': 'T', 'position_from': 1, 'position_to': 2,
            'level_from': 1, 'level_to': 1,
        }).action_generate()
        cls.loc1 = cls._location('T-01-1')
        cls.loc2 = cls._location('T-02-1')

    @classmethod
    def _location(cls, barcode):
        return cls.env['stock.location'].search([('barcode', '=', barcode)], limit=1)

    def _receive(self, lines=None, count=1, owner=None, location=None):
        wizard = self.env['stock.pallet.receive'].create({
            'warehouse_id': self.warehouse.id,
            'owner_id': (owner or self.owner).id,
            'origin': 'REM-001',
            'pallet_count': count,
            'location_dest_id': location.id if location else False,
            'line_ids': [Command.create(vals) for vals in (lines or [
                {'product_id': self.product.id, 'quantity': 100}])],
        })
        wizard.action_confirm()
        return wizard

    def _scan(self, mode, *codes, **vals):
        wizard = self.env['stock.pallet.scan'].create({'mode': mode, **vals})
        for code in codes:
            wizard.on_barcode_scanned(code)
        return wizard

    # ------------------------------------------------------------------ entrada
    def test_receive_creates_validated_receipt_with_package_and_owner(self):
        wizard = self._receive()
        self.assertEqual(wizard.state, 'done')
        picking = wizard.picking_id
        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.picking_type_code, 'incoming')
        package = wizard.package_ids
        self.assertEqual(len(package), 1)
        self.assertEqual(package.package_type_id, self.env.ref('stock_pallet_control.package_type_tarima'))
        self.assertEqual(package.location_id, self.loc1, 'Debe ir a la primera ubicación libre')
        self.assertEqual(package.owner_id, self.owner)
        quant = package.quant_ids
        self.assertEqual(quant.product_id, self.product)
        self.assertEqual(quant.quantity, 100)
        self.assertEqual(quant.owner_id, self.owner)

    def test_receive_several_equal_pallets_each_in_its_own_location(self):
        wizard = self._receive(count=2)
        self.assertEqual(len(wizard.package_ids), 2)
        self.assertEqual(set(wizard.package_ids.location_id.ids), {self.loc1.id, self.loc2.id})
        self.assertEqual(wizard.picking_id.state, 'done')
        total = sum(wizard.package_ids.quant_ids.mapped('quantity'))
        self.assertEqual(total, 200)

    def test_receive_fails_when_no_free_location(self):
        self._receive(count=2)
        with self.assertRaises(UserError):
            self._receive(count=1)

    def test_receive_mixed_pallet(self):
        wizard = self._receive(lines=[
            {'product_id': self.product.id, 'quantity': 10},
            {'product_id': self.product_b.id, 'quantity': 24},
        ])
        quants = wizard.package_ids.quant_ids
        self.assertEqual(quants.product_id, self.product | self.product_b)
        self.assertEqual(len(wizard.package_ids), 1)

    def test_receive_tracked_product_requires_lot(self):
        with self.assertRaises(UserError):
            self._receive(lines=[{'product_id': self.product_lot.id, 'quantity': 5}])
        wizard = self._receive(lines=[
            {'product_id': self.product_lot.id, 'quantity': 5, 'lot_name': 'L-2026-01'}])
        self.assertEqual(wizard.package_ids.quant_ids.lot_id.name, 'L-2026-01')

    # ------------------------------------------------------------------ ubicaciones
    def test_location_free_and_occupied_filters(self):
        self._receive()
        Location = self.env['stock.location']
        occupied = Location.search([('pallet_state', '=', 'occupied'), ('barcode', 'like', 'T-')])
        free = Location.search([('pallet_state', '=', 'free'), ('barcode', 'like', 'T-')])
        self.assertEqual(occupied, self.loc1)
        self.assertEqual(free, self.loc2)
        not_free = Location.search([('pallet_state', '!=', 'free'), ('barcode', 'like', 'T-')])
        self.assertEqual(not_free, self.loc1)
        self.assertEqual(self.loc1.pallet_count, 1)
        self.assertEqual(self.loc1.pallet_owner_ids, self.owner)
        self.assertEqual(self.loc2.pallet_state, 'free')

    # ------------------------------------------------------------------ escáner: salida
    def test_exit_by_scanning_the_label(self):
        package = self._receive().package_ids
        scan = self._scan('exit', package.name, partner_id=self.customer.id)
        self.assertTrue(scan.last_scan_ok)
        self.assertEqual(scan.package_ids, package)
        scan.action_confirm()
        self.assertEqual(scan.state, 'done')
        picking = scan.picking_ids
        self.assertEqual(picking.picking_type_code, 'outgoing')
        self.assertEqual(picking.state, 'done')
        self.assertEqual(package.location_id.usage, 'customer')
        self.assertEqual(package.owner_id, self.owner, 'El propietario viaja con la tarima')
        self.assertEqual(self.loc1.pallet_state, 'free', 'El espacio debe quedar libre')

    def test_exit_rejects_unknown_duplicate_and_already_gone(self):
        package = self._receive().package_ids
        scan = self._scan('exit', 'NO-EXISTE')
        self.assertFalse(scan.last_scan_ok)
        scan.on_barcode_scanned(package.name)
        scan.on_barcode_scanned(package.name)
        self.assertFalse(scan.last_scan_ok, 'Escanear dos veces la misma tarima debe avisar')
        self.assertEqual(len(scan.package_ids), 1)
        scan.action_confirm()
        again = self._scan('exit', package.name)
        self.assertFalse(again.last_scan_ok, 'Una tarima que ya salió no se puede sacar otra vez')
        self.assertFalse(again.package_ids)

    def test_exit_requires_a_scanned_pallet(self):
        with self.assertRaises(UserError):
            self._scan('exit').action_confirm()

    def test_exit_two_owners_creates_one_picking_per_owner(self):
        other_owner = self.env['res.partner'].create({'name': 'Otro Dueño SA'})
        pallet_a = self._receive().package_ids
        pallet_b = self._receive(owner=other_owner).package_ids
        scan = self._scan('exit', pallet_a.name, pallet_b.name)
        scan.action_confirm()
        self.assertEqual(len(scan.picking_ids), 2)
        self.assertEqual(set(scan.picking_ids.mapped('owner_id').ids), {self.owner.id, other_owner.id})

    # ------------------------------------------------------------------ escáner: mover
    def test_move_pallet_to_another_location(self):
        package = self._receive().package_ids
        scan = self._scan('move', package.name, 'T-02-1')
        self.assertEqual(scan.location_dest_id, self.loc2)
        scan.action_confirm()
        self.assertEqual(scan.picking_ids.picking_type_code, 'internal')
        self.assertEqual(scan.picking_ids.state, 'done')
        self.assertEqual(package.location_id, self.loc2)
        self.assertEqual(self.loc1.pallet_state, 'free')
        self.assertEqual(self.loc2.pallet_state, 'occupied')
        self.assertEqual(package.owner_id, self.owner)

    def test_move_to_occupied_location_is_rejected(self):
        wizard = self._receive(count=2)
        first, second = wizard.package_ids.sorted('id')
        scan = self._scan('move', first.name, second.location_id.barcode)
        with self.assertRaises(UserError):
            scan.action_confirm()

    def test_move_requires_destination(self):
        package = self._receive().package_ids
        with self.assertRaises(UserError):
            self._scan('move', package.name).action_confirm()

    # ------------------------------------------------------------------ etiqueta
    def test_label_report_renders_barcode_name_and_owner(self):
        package = self._receive().package_ids
        html, _fmt = self.env['ir.actions.report']._render_qweb_html(
            'stock_pallet_control.report_pallet_label', package.ids)
        html = html.decode()
        self.assertIn(package.name, html)
        self.assertIn('Cliente Dueño SA', html)
        self.assertIn('Caja de prueba', html)
        self.assertIn('data:image/png;base64', html, 'Debe incluir la imagen del código de barras')

    # ------------------------------------------------------------------ configuración
    def test_internal_users_get_pallet_features(self):
        user = self.env['res.users'].create({
            'name': 'Operador', 'login': 'operador_tarimas',
            'groups_id': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('stock.group_stock_user').id])],
        })
        for xmlid in ('stock.group_stock_multi_locations', 'stock.group_tracking_lot',
                      'stock.group_tracking_owner'):
            self.assertTrue(user.has_group(xmlid), xmlid)

    def test_full_flow_as_regular_warehouse_user(self):
        """El operador de almacén (no administrador) puede hacer todo el flujo."""
        operator = self.env['res.users'].create({
            'name': 'Operador Almacén', 'login': 'operador_almacen',
            'groups_id': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('stock.group_stock_user').id])],
        })
        env_user = self.env(user=operator)
        receive = env_user['stock.pallet.receive'].create({
            'warehouse_id': self.warehouse.id,
            'owner_id': self.owner.id,
            'line_ids': [Command.create({'product_id': self.product.id, 'quantity': 50})],
        })
        receive.action_confirm()
        package = receive.package_ids
        self.assertEqual(receive.picking_id.state, 'done')
        receive.action_print_labels()
        move = env_user['stock.pallet.scan'].create({'mode': 'move'})
        move.on_barcode_scanned(package.name)
        move.on_barcode_scanned('T-02-1')
        move.action_confirm()
        self.assertEqual(package.location_id, self.loc2)
        out = env_user['stock.pallet.scan'].create({'mode': 'exit'})
        out.on_barcode_scanned(package.name)
        out.action_confirm()
        self.assertEqual(package.location_id.usage, 'customer')

    def test_location_generator_is_idempotent(self):
        generator = self.env['stock.pallet.location.generator'].create({
            'prefix': 'T', 'position_from': 1, 'position_to': 3,
            'level_from': 1, 'level_to': 1,
        })
        action = generator.action_generate()
        created = self.env['stock.location'].search(action['domain'])
        self.assertEqual(created.mapped('barcode'), ['T-03-1'], 'Solo crea la que faltaba')
        self.assertEqual(created.location_id.usage, 'view', 'El rack no guarda mercancía')
