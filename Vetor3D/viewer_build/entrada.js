// Entrada dos bundles do código copia-e-cola: expõe o visualizador como
// window.Vetor3DViewer (uma vez só, mesmo com vários modelos na página).
import * as V from '../../static/localtools/vetor3d/viewer.js';

if (!window.Vetor3DViewer) {
  window.Vetor3DViewer = V;
  window.dispatchEvent(new Event('vetor3d:pronto'));
}
