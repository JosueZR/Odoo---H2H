/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Dashboard principal de operaciones de almacén.
 * Registrado como client action "stock_pallet_control.inventory_dashboard".
 * Cada tarjeta llama a una acción de Odoo existente, sin duplicar lógica.
 */
export class InventoryDashboard extends Component {
    static template = "stock_pallet_control.InventoryDashboard";

    setup() {
        this.action = useService("action");
        this.state = useState({
            isFullscreen: !!document.fullscreenElement,
        });

        this._onFullscreenChange = () => {
            this.state.isFullscreen = !!document.fullscreenElement;
        };

        onMounted(() => {
            document.addEventListener("fullscreenchange", this._onFullscreenChange);
        });

        onWillUnmount(() => {
            document.removeEventListener("fullscreenchange", this._onFullscreenChange);
        });
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            const el = document.documentElement;
            if (el.requestFullscreen) {
                el.requestFullscreen().catch(() => {});
            } else if (el.webkitRequestFullscreen) {
                el.webkitRequestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(() => {});
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
        }
    }

    // ── Recibir tarimas (wizard) ──────────────────────────────────────────────
    async openRecibirTarimas() {
        await this.action.doAction("stock_pallet_control.action_pallet_receive");
    }

    // ── Ver recepciones (lista estándar) ──────────────────────────────────────
    async openRecepciones() {
        await this.action.doAction({
            name: "Recepciones",
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["picking_type_code", "=", "incoming"]],
            context: { default_picking_type_code: "incoming" },
        });
    }

    // ── Mapa de ubicaciones ───────────────────────────────────────────────────
    async openMapa() {
        await this.action.doAction("stock_pallet_control.action_pallet_locations");
    }

    // ── Generar ubicaciones ───────────────────────────────────────────────────
    async openGenerador() {
        await this.action.doAction("stock_pallet_control.action_pallet_location_generator");
    }

    // ── Salidas (wizard escaneo) ──────────────────────────────────────────────
    async openSalidas() {
        await this.action.doAction("stock_pallet_control.action_pallet_scan", {
            additionalContext: { default_mode: "exit" },
        });
    }

    // ── Movimientos internos (wizard escaneo) ─────────────────────────────────
    async openInternos() {
        await this.action.doAction("stock_pallet_control.action_pallet_scan", {
            additionalContext: { default_mode: "move" },
        });
    }

    // ── Inventario / Existencias ──────────────────────────────────────────────
    async openInventario() {
        await this.action.doAction("stock.location_open_quants");
    }
}

registry
    .category("actions")
    .add("stock_pallet_control.inventory_dashboard", InventoryDashboard);
