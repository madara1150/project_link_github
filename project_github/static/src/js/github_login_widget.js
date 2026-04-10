/** @odoo-module **/

import { Component, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class GithubLoginButton extends Component {
    static template = xml`
        <button t-on-click="onDisconnect"
                class="btn btn-secondary btn-sm d-inline-flex align-items-center gap-2"
                t-att-disabled="state.loading">
            <img t-if="avatarUrl"
                 t-att-src="avatarUrl"
                 style="width:20px;height:20px;border-radius:50%;object-fit:cover;"
                 alt="GitHub avatar"/>
            <i t-else="" class="fa fa-github"/>
            <t t-esc="props.value"/>
        </button>
    `;
    static props = { ...standardFieldProps };
    static supportedTypes = ["char"];

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = useState({ loading: false });
    }

    get avatarUrl() {
        return this.props.record.data.github_avatar_url || '';
    }

    onDisconnect() {
        this.dialog.add(ConfirmationDialog, {
            body: _t("This will remove your stored GitHub token. Are you sure?"),
            confirm: async () => {
                this.state.loading = true;
                await this.orm.call(
                    this.props.record.resModel,
                    "action_github_disconnect",
                    [this.props.record.resId],
                );
                await this.props.record.model.load();
                this.state.loading = false;
            },
        });
    }
}

registry.category("fields").add("github_login_button", GithubLoginButton);
