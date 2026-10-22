/** Utilidades compartidas de la interfaz. */
export const $ = id => document.getElementById(id);
export const number = new Intl.NumberFormat('es-ES');
export function set(id, value) {
 const element = $(id);
 const text = String(value);
 if (element.textContent !== text) element.textContent = text;
}
