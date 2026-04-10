/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Service that checks for a pending GitHub OAuth notification stored in the
 * server-side session and displays it via Odoo's notification service.
 *
 * The notification is written by the OAuth callback controller and is cleared
 * (popped) on the first call to /github/notification, so it shows only once.
 */
const githubNotificationService = {
    dependencies: ["notification", "rpc"],
    async start(env, { notification, rpc }) {
        try {
            const notif = await rpc("/github/notification");
            if (notif) {
                notification.add(notif.message, {
                    title: notif.title,
                    type: notif.type,
                    sticky: notif.type === "danger",
                });
            }
        } catch (_) {
            // Silently ignore — non-critical feature
        }
    },
};

registry.category("services").add("github_notification_service", githubNotificationService);
