export function appendLog(msg, type = 'info') {
    const terminal = document.getElementById('terminal');
    if (!terminal) return;
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    line.textContent = msg;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

export function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

export function safeHttpUrl(value) {
    try {
        const parsed = new URL(String(value || ''), window.location.origin);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
    } catch (_) {
        return '';
    }
}

export function showToast(message, type = 'warning') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    // Icon based on type
    let icon = '';
    if (type === 'warning' || type === 'error') {
        icon = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else if (type === 'success') {
        icon = `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`;
    }
    
    if (icon) toast.insertAdjacentHTML('beforeend', icon);
    const messageEl = document.createElement('span');
    messageEl.textContent = String(message ?? '');
    toast.appendChild(messageEl);
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fadeOut');
        toast.addEventListener('animationend', () => {
            toast.remove();
        });
    }, 3000);
}

export function formatTimeSec(seconds) {
    if (isNaN(seconds) || seconds < 0) return "00:00:00";
    let hrs = Math.floor(seconds / 3600);
    let mins = Math.floor((seconds % 3600) / 60);
    let secs = Math.floor(seconds % 60);
    hrs = hrs < 10 ? '0' + hrs : hrs;
    mins = mins < 10 ? '0' + mins : mins;
    secs = secs < 10 ? '0' + secs : secs;
    return `${hrs}:${mins}:${secs}`;
}

export function parseTimeToSeconds(timeStr) {
    if (typeof timeStr === 'number') return timeStr;
    if (!timeStr) return 0;
    try {
        const cleaned = timeStr.trim().replace(',', '.');
        const parts = cleaned.split(':');
        if (parts.length === 3) {
            return parseInt(parts[0], 10) * 3600 + parseInt(parts[1], 10) * 60 + parseFloat(parts[2]);
        } else if (parts.length === 2) {
            return parseInt(parts[0], 10) * 60 + parseFloat(parts[1]);
        }
        return parseFloat(cleaned) || 0;
    } catch(e) {
        return 0;
    }
}

export function formatSrtTimestamp(seconds) {
    if (isNaN(seconds) || seconds < 0) seconds = 0;
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    const pad = (n, len = 2) => String(n).padStart(len, '0');
    return `${pad(hrs)}:${pad(mins)}:${pad(secs)},${pad(ms, 3)}`;
}

export function formatDurationStr(seconds) {
    if (!seconds || isNaN(seconds)) return '00:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hrs > 0) {
        return `${hrs}:${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

// ═════════════════════════════════════════════════════════════
// 🌟 HỆ THỐNG HỘP THOẠI QUY CHUẨN ĐỒNG BỘ (UNIFIED APP DIALOGS)
// ═════════════════════════════════════════════════════════════

const COLOR_MAP = {
    danger: { border: '#ef4444', glow: 'rgba(239, 68, 68, 0.25)', btnBg: 'linear-gradient(135deg, #ef4444, #dc2626)', iconBg: 'rgba(239, 68, 68, 0.15)', iconColor: '#f87171' },
    warning: { border: '#f59e0b', glow: 'rgba(245, 158, 11, 0.25)', btnBg: 'linear-gradient(135deg, #f59e0b, #d97706)', iconBg: 'rgba(245, 158, 11, 0.15)', iconColor: '#fbbf24' },
    primary: { border: '#38bdf8', glow: 'rgba(56, 189, 248, 0.25)', btnBg: 'linear-gradient(135deg, #0ea5e9, #6366f1)', iconBg: 'rgba(14, 165, 233, 0.15)', iconColor: '#38bdf8' },
    success: { border: '#10b981', glow: 'rgba(16, 185, 129, 0.25)', btnBg: 'linear-gradient(135deg, #10b981, #059669)', iconBg: 'rgba(16, 185, 129, 0.15)', iconColor: '#34d399' }
};

/**
 * Hộp thoại Xác nhận Chuẩn Dark Theme (Thay thế window.confirm)
 * Hỗ trợ cả 2 cú pháp: showConfirmModal({title, message}) HOẶC showConfirmModal(title, message, icon)
 */
export function showConfirmModal(opts = {}) {
    let title = 'XÁC NHẬN THAO TÁC', message = '', icon = '❓', confirmText = 'Xác Nhận', cancelText = 'Hủy', confirmType = 'primary';
    if (typeof opts === 'string') {
        title = arguments[0] || title;
        message = arguments[1] || '';
        icon = arguments[2] || icon;
        confirmText = arguments[3] || confirmText;
        cancelText = arguments[4] || cancelText;
        confirmType = arguments[5] || confirmType;
    } else if (typeof opts === 'object' && opts !== null) {
        title = opts.title || title;
        message = opts.message || '';
        icon = opts.icon || icon;
        confirmText = opts.confirmText || confirmText;
        cancelText = opts.cancelText || cancelText;
        confirmType = opts.confirmType || confirmType;
    }

    return new Promise((resolve) => {
        const existing = document.getElementById('universalConfirmModal');
        if (existing) existing.remove();

        const theme = COLOR_MAP[confirmType] || COLOR_MAP.primary;

        const overlay = document.createElement('div');
        overlay.id = 'universalConfirmModal';
        overlay.className = 'modal-overlay';
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
            z-index: 999999; display: flex; align-items: center; justify-content: center;
            animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        `;

        overlay.innerHTML = `
            <div style="background: #0f172a; border: 1px solid ${theme.border}; border-radius: 14px; width: 440px; max-width: 92vw; padding: 22px 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 0 25px ${theme.glow}; animation: popInCelebration 0.2s cubic-bezier(0.16, 1, 0.3, 1); display: flex; flex-direction: column; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 44px; height: 44px; border-radius: 10px; background: ${theme.iconBg}; border: 1px solid ${theme.border}; display: flex; align-items: center; justify-content: center; font-size: 22px; color: ${theme.iconColor}; flex-shrink: 0;">
                        ${escapeHtml(icon)}
                    </div>
                    <div>
                        <h3 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0; letter-spacing: 0.3px;">${escapeHtml(title)}</h3>
                        <div style="font-size: 11.5px; color: #94a3b8; margin-top: 2px;">Xác nhận hành động từ ứng dụng</div>
                    </div>
                </div>

                <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid #334155; border-radius: 10px; padding: 14px 16px; font-size: 13.5px; line-height: 1.6; color: #e2e8f0;">
                    ${escapeHtml(message)}
                </div>

                <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px;">
                    <button type="button" id="btnUniversalCancel" class="btn secondary" style="padding: 9px 18px; font-size: 13px; font-weight: 600; background: #1e293b; border: 1px solid #475569; color: #cbd5e1; border-radius: 8px; cursor: pointer; transition: all 0.15s;">
                        ${escapeHtml(cancelText)}
                    </button>
                    <button type="button" id="btnUniversalConfirm" class="btn" style="padding: 9px 22px; font-size: 13px; font-weight: 700; background: ${theme.btnBg}; color: #fff; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px ${theme.glow}; transition: all 0.15s;">
                        ${escapeHtml(confirmText)}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const btnConfirm = overlay.querySelector('#btnUniversalConfirm');
        const btnCancel = overlay.querySelector('#btnUniversalCancel');

        const cleanup = (result) => {
            document.removeEventListener('keydown', onKey);
            overlay.remove();
            resolve(result);
        };

        const onKey = (e) => {
            if (e.key === 'Escape') cleanup(false);
            if (e.key === 'Enter') cleanup(true);
        };

        document.addEventListener('keydown', onKey);
        btnConfirm.addEventListener('click', () => cleanup(true));
        btnCancel.addEventListener('click', () => cleanup(false));
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup(false);
        });

        btnConfirm.focus();
    });
}

/**
 * Hộp thoại Thông báo Chuẩn Dark Theme (Thay thế window.alert)
 * Hỗ trợ cả 2 cú pháp: showAlertModal({title, message}) HOẶC showAlertModal(title, message, icon)
 */
export function showAlertModal(opts = {}) {
    let title = 'THÔNG BÁO', message = '', icon = 'ℹ️', buttonText = 'Đã Hiểu', type = 'primary', buttons = null;
    if (typeof opts === 'string') {
        title = arguments[0] || title;
        message = arguments[1] || '';
        icon = arguments[2] || icon;
        buttonText = arguments[3] || buttonText;
        type = arguments[4] || type;
    } else if (typeof opts === 'object' && opts !== null) {
        title = opts.title || title;
        message = opts.message || '';
        icon = opts.icon || icon;
        buttonText = opts.buttonText || buttonText;
        type = opts.type || type;
        buttons = opts.buttons || null;
    }

    return new Promise((resolve) => {
        const existing = document.getElementById('universalAlertModal');
        if (existing) existing.remove();

        const theme = COLOR_MAP[type] || COLOR_MAP.primary;

        const overlay = document.createElement('div');
        overlay.id = 'universalAlertModal';
        overlay.className = 'modal-overlay';
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
            z-index: 999999; display: flex; align-items: center; justify-content: center;
            animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        `;

        let buttonsHtml = '';
        if (Array.isArray(buttons) && buttons.length > 0) {
            buttonsHtml = `<div style="display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; margin-top: 4px;">`;
            buttons.forEach((btn, idx) => {
                const btnBg = btn.primary ? theme.btnBg : (btn.danger ? '#ef4444' : 'rgba(255,255,255,0.08)');
                const btnColor = btn.primary || btn.danger ? '#fff' : '#cbd5e1';
                const btnBorder = btn.primary || btn.danger ? 'none' : '1px solid #475569';
                buttonsHtml += `
                    <button type="button" class="btn custom-alert-btn" data-btn-idx="${idx}" style="padding: 9px 18px; font-size: 13px; font-weight: 600; background: ${btnBg}; color: ${btnColor}; border: ${btnBorder}; border-radius: 8px; cursor: pointer; transition: all 0.15s;">
                        ${escapeHtml(btn.text)}
                    </button>
                `;
            });
            buttonsHtml += `</div>`;
        } else {
            buttonsHtml = `
                <div style="display: flex; justify-content: flex-end; margin-top: 4px;">
                    <button type="button" id="btnUniversalAlertOk" class="btn" style="padding: 9px 26px; font-size: 13px; font-weight: 700; background: ${theme.btnBg}; color: #fff; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px ${theme.glow}; transition: all 0.15s;">
                        ${escapeHtml(buttonText)}
                    </button>
                </div>
            `;
        }

        overlay.innerHTML = `
            <div style="background: #0f172a; border: 1px solid ${theme.border}; border-radius: 14px; width: 460px; max-width: 92vw; padding: 22px 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 0 25px ${theme.glow}; animation: popInCelebration 0.2s cubic-bezier(0.16, 1, 0.3, 1); display: flex; flex-direction: column; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 44px; height: 44px; border-radius: 10px; background: ${theme.iconBg}; border: 1px solid ${theme.border}; display: flex; align-items: center; justify-content: center; font-size: 22px; color: ${theme.iconColor}; flex-shrink: 0;">
                        ${escapeHtml(icon)}
                    </div>
                    <div>
                        <h3 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0; letter-spacing: 0.3px;">${escapeHtml(title)}</h3>
                        <div style="font-size: 11.5px; color: #94a3b8; margin-top: 2px;">Thông báo từ hệ thống</div>
                    </div>
                </div>

                <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid #334155; border-radius: 10px; padding: 14px 16px; font-size: 13.5px; line-height: 1.6; color: #e2e8f0;">
                    ${escapeHtml(message)}
                </div>

                ${buttonsHtml}
            </div>
        `;

        document.body.appendChild(overlay);

        const cleanup = (val) => {
            document.removeEventListener('keydown', onKey);
            overlay.remove();
            resolve(val);
        };

        const onKey = (e) => {
            if (e.key === 'Escape' || e.key === 'Enter') cleanup(null);
        };

        document.addEventListener('keydown', onKey);
        
        if (Array.isArray(buttons) && buttons.length > 0) {
            overlay.querySelectorAll('.custom-alert-btn').forEach(btnEl => {
                btnEl.addEventListener('click', () => {
                    const idx = parseInt(btnEl.getAttribute('data-btn-idx'), 10);
                    const btnDef = buttons[idx];
                    cleanup(btnDef ? btnDef.value || btnDef.text : null);
                    if (btnDef && typeof btnDef.onClick === 'function') {
                        btnDef.onClick();
                    }
                });
            });
        } else {
            const btnOk = overlay.querySelector('#btnUniversalAlertOk');
            if (btnOk) {
                btnOk.addEventListener('click', () => cleanup('ok'));
                btnOk.focus();
            }
        }

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup(null);
        });
    });
}

/**
 * Hộp thoại Nhập liệu Chuẩn Dark Theme (Thay thế window.prompt)
 * Hỗ trợ cả 2 cú pháp: showPromptModal({title, message}) HOẶC showPromptModal(title, message, placeholder, defaultValue)
 */
export function showPromptModal(opts = {}) {
    let title = 'NHẬP THÔNG TIN', message = '', placeholder = 'Nhập nội dung...', defaultValue = '', icon = '✏️', confirmText = 'Đồng Ý', cancelText = 'Hủy';
    if (typeof opts === 'string') {
        title = arguments[0] || title;
        message = arguments[1] || '';
        placeholder = arguments[2] || placeholder;
        defaultValue = arguments[3] || defaultValue;
        icon = arguments[4] || icon;
        confirmText = arguments[5] || confirmText;
        cancelText = arguments[6] || cancelText;
    } else if (typeof opts === 'object' && opts !== null) {
        title = opts.title || title;
        message = opts.message || '';
        placeholder = opts.placeholder || placeholder;
        defaultValue = opts.defaultValue || defaultValue;
        icon = opts.icon || icon;
        confirmText = opts.confirmText || confirmText;
        cancelText = opts.cancelText || cancelText;
    }
    return new Promise((resolve) => {
        const existing = document.getElementById('universalPromptModal');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'universalPromptModal';
        overlay.className = 'modal-overlay';
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
            z-index: 999999; display: flex; align-items: center; justify-content: center;
            animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
        `;

        overlay.innerHTML = `
            <div style="background: #0f172a; border: 1px solid #38bdf8; border-radius: 14px; width: 440px; max-width: 92vw; padding: 22px 24px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 0 25px rgba(56, 189, 248, 0.25); animation: popInCelebration 0.2s cubic-bezier(0.16, 1, 0.3, 1); display: flex; flex-direction: column; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 44px; height: 44px; border-radius: 10px; background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; display: flex; align-items: center; justify-content: center; font-size: 22px; color: #38bdf8; flex-shrink: 0;">
                        ${escapeHtml(icon)}
                    </div>
                    <div>
                        <h3 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0; letter-spacing: 0.3px;">${escapeHtml(title)}</h3>
                        <div style="font-size: 11.5px; color: #94a3b8; margin-top: 2px;">Vui lòng điền thông tin bên dưới</div>
                    </div>
                </div>

                ${message ? `<div style="font-size: 13px; color: #cbd5e1;">${escapeHtml(message)}</div>` : ''}

                <div>
                    <input type="text" id="inputUniversalPromptVal" class="text-input" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(defaultValue)}" style="width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 13.5px;">
                </div>

                <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px;">
                    <button type="button" id="btnUniversalPromptCancel" class="btn secondary" style="padding: 9px 18px; font-size: 13px; font-weight: 600; background: #1e293b; border: 1px solid #475569; color: #cbd5e1; border-radius: 8px; cursor: pointer;">
                        ${escapeHtml(cancelText)}
                    </button>
                    <button type="button" id="btnUniversalPromptConfirm" class="btn primary-cyan" style="padding: 9px 22px; font-size: 13px; font-weight: 700; background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(56, 189, 248, 0.35);">
                        ${escapeHtml(confirmText)}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const inputEl = overlay.querySelector('#inputUniversalPromptVal');
        const btnConfirm = overlay.querySelector('#btnUniversalPromptConfirm');
        const btnCancel = overlay.querySelector('#btnUniversalPromptCancel');

        const cleanup = (result) => {
            document.removeEventListener('keydown', onKey);
            overlay.remove();
            resolve(result);
        };

        const onKey = (e) => {
            if (e.key === 'Escape') cleanup(null);
            if (e.key === 'Enter') cleanup(inputEl ? inputEl.value.trim() : '');
        };

        document.addEventListener('keydown', onKey);
        btnConfirm.addEventListener('click', () => cleanup(inputEl ? inputEl.value.trim() : ''));
        btnCancel.addEventListener('click', () => cleanup(null));
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup(null);
        });

        inputEl.focus();
        inputEl.select();
    });
}

// Gắn toàn cục lên window để mọi module đều có thể gọi
if (typeof window !== 'undefined') {
    window.showConfirmModal = showConfirmModal;
    window.showAlertModal = showAlertModal;
    window.showPromptModal = showPromptModal;
}

