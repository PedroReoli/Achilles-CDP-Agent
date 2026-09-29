"""Detecção de desafios (Cloudflare, CAPTCHA, 2FA/OTP) e handshake com usuário."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional
from urllib.parse import urlsplit

from .errors import ServiceError
from .hud import HudManager
from .session_manager import BrowserSessionManager

if TYPE_CHECKING:
    pass

LOG = logging.getLogger(__name__)

EVALUATE_CHALLENGE_JS = r"""() => {
    // 1. Cloudflare Turnstile / Challenge Stage
    const cf = document.querySelector(
        'iframe[src*="cloudflare"], iframe[src*="challenges.cloudflare.com"], #challenge-stage, .cf-turnstile, #turnstile-wrapper'
    );
    if (cf) {
        return {
            detected: true,
            type: 'cloudflare_turnstile',
            name: 'Cloudflare Turnstile / Managed Challenge',
            description: 'Verificação de segurança ativa da Cloudflare.'
        };
    }

    // 2. Google reCAPTCHA
    const recaptcha = document.querySelector(
        'iframe[src*="google.com/recaptcha"], iframe[title*="reCAPTCHA"], .g-recaptcha, #recaptcha'
    );
    if (recaptcha) {
        return {
            detected: true,
            type: 'google_recaptcha',
            name: 'Google reCAPTCHA',
            description: 'Desafio interativo Google reCAPTCHA v2/v3 detectado.'
        };
    }

    // 3. hCaptcha
    const hcaptcha = document.querySelector(
        'iframe[src*="hcaptcha.com"], .h-captcha, iframe[data-hcaptcha-widget-id]'
    );
    if (hcaptcha) {
        return {
            detected: true,
            type: 'hcaptcha',
            name: 'hCaptcha',
            description: 'Desafio hCaptcha ativo.'
        };
    }

    // 4. Arkose Labs / FunCAPTCHA
    const arkose = document.querySelector(
        'iframe[src*="arkoselabs"], iframe[src*="funcaptcha"], #fc-iframe-wrap'
    );
    if (arkose) {
        return {
            detected: true,
            type: 'arkose_funcaptcha',
            name: 'Arkose Labs FunCAPTCHA',
            description: 'Desafio Arkose Labs / FunCAPTCHA detectado.'
        };
    }

    // 5. AWS WAF Captcha
    const awsWaf = document.querySelector('#aws-waf-captcha, iframe[src*="awswaf"]');
    if (awsWaf) {
        return {
            detected: true,
            type: 'aws_waf_captcha',
            name: 'AWS WAF CAPTCHA',
            description: 'Desafio AWS WAF CAPTCHA detectado.'
        };
    }

    // 6. Two-Factor Authentication / OTP / SMS Code input
    const otpInput = document.querySelector(
        'input[autocomplete="one-time-code"], input[name*="otp" i], input[name*="2fa" i], input[id*="otp" i], input[id*="2fa" i], input[placeholder*="código" i], input[placeholder*="code" i]'
    );
    if (otpInput && !otpInput.value) {
        return {
            detected: true,
            type: '2fa_otp_required',
            name: 'Autenticação de Dois Fatores (2FA/OTP)',
            description: 'A página aguarda preenchimento de código de verificação 2FA/SMS.'
        };
    }

    // 7. Login Wall / Password Prompt
    const passInput = document.querySelector('input[type="password"]');
    if (passInput && passInput.offsetParent !== null) {
        return {
            detected: true,
            type: 'login_required',
            name: 'Tela de Autenticação / Login',
            description: 'A página requer login do usuário humano.'
        };
    }

    return { detected: false, type: 'none', name: '', description: '' };
}"""


class ChallengeEngine:
    """Gerencia a detecção de desafios antibot e o handshake colaborativo humano-IA."""

    def __init__(self, session: BrowserSessionManager) -> None:
        self.session = session

    async def detect(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Detecta se há desafio ou barreira de autenticação na aba informada."""
        key, page = await self.session.page(page_id)
        if page.is_closed():
            raise ServiceError("PAGE_CLOSED", "A aba foi fechada.")

        async with self.session.registry.locks[key]:
            try:
                result = await page.evaluate(EVALUATE_CHALLENGE_JS)
                result["page_id"] = key
                result["url"] = page.url
                return result
            except Exception as exc:
                LOG.debug("Falha ao avaliar desafios na página: %s", exc)
                return {"detected": False, "type": "none", "page_id": key, "url": page.url}

    async def wait_for_resolution(
        self,
        page_id: Optional[str] = None,
        timeout_s: int = 120,
        poll_interval_s: float = 1.0,
    ) -> Dict[str, Any]:
        """Bloqueia e aguarda o usuário humano resolver o desafio ou mudar de página."""
        key, page = await self.session.page(page_id)
        if page.is_closed():
            raise ServiceError("PAGE_CLOSED", "A aba foi fechada.")

        initial_url = page.url
        start_time = time.time()
        timeout_s = min(max(timeout_s, 5), 600)

        initial_check = await self.detect(key)
        if not initial_check.get("detected"):
            return {
                "status": "already_clear",
                "message": "Nenhum desafio ou login detectado no momento.",
                "page_id": key,
                "url": page.url,
                "elapsed_s": 0.0,
            }

        # Notifica o HUD in-browser com status waiting_human
        await HudManager.update(
            page,
            status="waiting_human",
            message=f"Aguardando você: {initial_check.get('name', 'Desafio / Login')}",
        )

        while (time.time() - start_time) < timeout_s:
            await asyncio.sleep(poll_interval_s)

            if page.is_closed():
                return {
                    "status": "page_closed",
                    "message": "A aba foi fechada pelo usuário.",
                    "page_id": key,
                    "elapsed_s": round(time.time() - start_time, 1),
                }

            # 1. Checa se a URL mudou
            current_url = page.url
            if urlsplit(current_url).path != urlsplit(initial_url).path:
                await HudManager.update(page, status="idle", message="Navegação detectada! Achilles pronto.")
                return {
                    "status": "resolved_by_navigation",
                    "message": f"Navegação detectada: URL mudou de {initial_url} para {current_url}.",
                    "page_id": key,
                    "url": current_url,
                    "elapsed_s": round(time.time() - start_time, 1),
                }

            # 2. Checa se o elemento de desafio sumiu
            check = await self.detect(key)
            if not check.get("detected"):
                await HudManager.update(page, status="idle", message="Desafio resolvido! Achilles pronto.")
                return {
                    "status": "resolved",
                    "message": "Desafio resolvido com sucesso pelo usuário!",
                    "page_id": key,
                    "url": current_url,
                    "elapsed_s": round(time.time() - start_time, 1),
                }

        await HudManager.update(page, status="idle", message="Tempo esgotado no desafio.")
        return {
            "status": "timeout",
            "message": f"Tempo esgotado ({timeout_s}s) aguardando resolução humana.",
            "page_id": key,
            "url": page.url,
            "elapsed_s": round(time.time() - start_time, 1),
        }
