"""
Scripts JavaScript injectés dans chaque page pour masquer l'automatisation.
Inspiré des techniques de stealth utilisées par Puppeteer-extra-stealth.
"""

STEALTH_JS = """
// 1. Masquer navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// 2. Simuler des plugins de navigateur réels
const mockPlugins = [
    { name: 'Chrome PDF Plugin',  filename: 'internal-pdf-viewer',            description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer',  filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client',      filename: 'internal-nacl-plugin',            description: '' },
];
Object.defineProperty(navigator, 'plugins', {
    get: () => Object.assign(mockPlugins, {
        item: i  => mockPlugins[i],
        namedItem: n => mockPlugins.find(p => p.name === n) || null,
        refresh: () => {},
        length: mockPlugins.length,
    }),
});

// 3. Langues réalistes
Object.defineProperty(navigator, 'languages', {
    get: () => ['fr-FR', 'fr', 'en-US', 'en'],
});

// 4. Platform réaliste
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 5. Hardware concurrency (simuler 8 cœurs)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// 6. Device memory
if ('deviceMemory' in navigator) {
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
}

// 7. Chrome runtime (présent dans Chrome réel, absent dans Chromium automation)
if (!window.chrome) {
    window.chrome = {
        runtime: {
            id: undefined,
            connect:      function() { return { onMessage: { addListener: () => {} }, postMessage: () => {}, disconnect: () => {} }; },
            sendMessage:  function() {},
            onConnect:  { addListener: () => {} },
            onMessage:  { addListener: () => {} },
        },
        loadTimes: function() { return {}; },
        csi: function() { return {}; },
        app: {},
    };
}

// 8. Permissions : éviter les détections via notifications
if (navigator.permissions && navigator.permissions.query) {
    const _origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return _origQuery(params);
    };
}

// 9. Résolution d'écran réaliste
try {
    Object.defineProperty(screen, 'width',       { get: () => 1920 });
    Object.defineProperty(screen, 'height',      { get: () => 1080 });
    Object.defineProperty(screen, 'availWidth',  { get: () => 1920 });
    Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
    Object.defineProperty(screen, 'colorDepth',  { get: () => 24  });
    Object.defineProperty(screen, 'pixelDepth',  { get: () => 24  });
} catch(e) {}

// 10. WebGL vendor/renderer (ne pas laisser les valeurs par défaut de Swiftshader)
const _getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';           // UNMASKED_VENDOR_WEBGL
    if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return _getParam.call(this, param);
};
"""
