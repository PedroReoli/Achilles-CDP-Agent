"""
dom_parser.py — Extrator de DOM Semântico e Árvore de Acessibilidade Otimizada para LLMs.
"""
from typing import Dict, Any, List


class DOMSemanticParser:
    """Extrai elementos interativos com IDs numéricos para consumo de IA com baixo custo de tokens."""

    JS_EXTRACT_TREE = """
    () => {
        const interactiveSelectors = 'button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [tabindex="0"]';
        const elements = Array.from(document.querySelectorAll(interactiveSelectors));
        
        let idCounter = 1;
        const result = [];
        const forms = [];
        const links = [];

        for (const el of elements) {
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;

            const tag = el.tagName.toLowerCase();
            const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.title || '').trim();
            const role = el.getAttribute('role') || tag;
            const type = el.getAttribute('type') || '';
            const name = el.getAttribute('name') || el.id || '';

            const item = {
                id: idCounter++,
                tag: tag,
                role: role,
                type: type,
                name: name,
                text: text.substring(0, 100),
                disabled: el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true',
                bounds: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                }
            };

            result.push(item);

            if (['input', 'textarea', 'select'].includes(tag)) {
                forms.push(item);
            }
            if (tag === 'a' && el.href) {
                links.push({ id: item.id, text: item.text, href: el.href });
            }
        }

        return {
            title: document.title,
            url: window.location.href,
            elements: result,
            forms: forms,
            links: links
        };
    }
    """

    @staticmethod
    def format_tree_for_llm(elements: List[Dict[str, Any]]) -> str:
        lines = ["# SEMANTIC ACCESSIBILITY TREE (Use numeric ID for interactions)"]
        for el in elements:
            label = el.get("text") or el.get("name") or "Unnamed"
            tag_type = f"{el['tag']}:{el['type']}" if el.get("type") else el["tag"]
            disabled_flag = " [DISABLED]" if el.get("disabled") else ""
            lines.append(f'[#{el["id"]}] <{tag_type}> "{label}"{disabled_flag}')
        return "\n".join(lines)
