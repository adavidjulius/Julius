import SwiftUI
import WebKit
import JuliusCore

#if os(macOS)
import AppKit

final class NonScrollingWKWebView: WKWebView {
    override func scrollWheel(with event: NSEvent) {
        nextResponder?.scrollWheel(with: event)
    }
}

public struct KaTeXMathView: NSViewRepresentable {
    public let content: String
    @Binding public var dynamicHeight: CGFloat

    public init(content: String, dynamicHeight: Binding<CGFloat> = .constant(40)) {
        self.content = content
        self._dynamicHeight = dynamicHeight
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(content: content, dynamicHeight: $dynamicHeight)
    }

    public func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let userContent = WKUserContentController()
        userContent.add(context.coordinator, name: "heightHandler")
        config.userContentController = userContent

        let webView = NonScrollingWKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.setValue(false, forKey: "drawsBackground")
        context.coordinator.webView = webView

        let baseURL = Bundle.module.resourceURL ?? Bundle.main.bundleURL
        let html = KaTeXHTMLTemplate.buildHTML(for: content)
        webView.loadHTMLString(html, baseURL: baseURL)

        return webView
    }

    public func updateNSView(_ nsView: WKWebView, context: Context) {
        context.coordinator.dynamicHeight = _dynamicHeight
        context.coordinator.updateContent(content)
    }
}

#elseif os(iOS)
import UIKit

public struct KaTeXMathView: UIViewRepresentable {
    public let content: String
    @Binding public var dynamicHeight: CGFloat

    public init(content: String, dynamicHeight: Binding<CGFloat> = .constant(40)) {
        self.content = content
        self._dynamicHeight = dynamicHeight
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(content: content, dynamicHeight: $dynamicHeight)
    }

    public func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let userContent = WKUserContentController()
        userContent.add(context.coordinator, name: "heightHandler")
        config.userContentController = userContent

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.bounces = false
        webView.scrollView.backgroundColor = .clear
        context.coordinator.webView = webView

        let baseURL = Bundle.module.resourceURL ?? Bundle.main.bundleURL
        let html = KaTeXHTMLTemplate.buildHTML(for: content)
        webView.loadHTMLString(html, baseURL: baseURL)

        return webView
    }

    public func updateUIView(_ uiView: WKWebView, context: Context) {
        context.coordinator.dynamicHeight = _dynamicHeight
        context.coordinator.updateContent(content)
    }
}
#endif

// ── Coordinator for Height Feedback & Script Handling ─────────────────────────

@MainActor
public final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
    public var dynamicHeight: Binding<CGFloat>
    public var currentContent: String
    weak var webView: WKWebView?
    private var isLoaded: Bool = false
    private var pendingContent: String?

    init(content: String, dynamicHeight: Binding<CGFloat>) {
        self.currentContent = content
        self.dynamicHeight = dynamicHeight
        super.init()
    }

    public func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "heightHandler", let height = message.body as? NSNumber {
            let h = CGFloat(height.doubleValue)
            if h > 10 {
                DispatchQueue.main.async {
                    self.dynamicHeight.wrappedValue = h
                }
            }
        }
    }

    public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isLoaded = true
        let contentToLoad = pendingContent ?? currentContent
        pendingContent = nil
        executeScriptUpdate(contentToLoad)
    }

    public func updateContent(_ rawContent: String) {
        currentContent = rawContent
        guard isLoaded else {
            pendingContent = rawContent
            return
        }
        executeScriptUpdate(rawContent)
    }

    private func executeScriptUpdate(_ text: String) {
        guard let webView = webView else { return }
        let normalized = normalizeMathMarkdown(text)
        guard let jsonData = try? JSONSerialization.data(withJSONObject: [normalized]),
              let jsonArray = String(data: jsonData, encoding: .utf8) else { return }

        let jsonStr = String(jsonArray.dropFirst().dropLast())
        let script = """
        if (window.updateContent) {
            window.updateContent(\(jsonStr));
        }
        Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, (document.getElementById('content') ? document.getElementById('content').scrollHeight : 0));
        """
        webView.evaluateJavaScript(script) { [weak self] res, error in
            if let error = error {
                print("KaTeX JS error: \(error)")
            }
            if let h = res as? NSNumber, h.doubleValue > 10 {
                DispatchQueue.main.async {
                    self?.dynamicHeight.wrappedValue = CGFloat(h.doubleValue)
                }
            }
        }
    }

    public func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
        if navigationAction.navigationType == .linkActivated, let url = navigationAction.request.url {
            #if os(macOS)
            NSWorkspace.shared.open(url)
            #elseif os(iOS)
            UIApplication.shared.open(url)
            #endif
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }
}

// ── Standalone HTML & KaTeX CSS/JS Template ───────────────────────────────────

enum KaTeXHTMLTemplate {
    private static let cachedCSS: String = {
        if let url = Bundle.module.url(forResource: "katex.min", withExtension: "css"),
           let str = try? String(contentsOf: url, encoding: .utf8) {
            return str
        }
        return ""
    }()

    private static let cachedKaTeXJS: String = {
        if let url = Bundle.module.url(forResource: "katex.min", withExtension: "js"),
           let str = try? String(contentsOf: url, encoding: .utf8) {
            return str
        }
        return ""
    }()

    private static let cachedMarkedJS: String = {
        if let url = Bundle.module.url(forResource: "marked.min", withExtension: "js"),
           let str = try? String(contentsOf: url, encoding: .utf8) {
            return str
        }
        return ""
    }()

    static func buildHTML(for initialContent: String) -> String {
        let normalized = normalizeMathMarkdown(initialContent)
        let jsonData = (try? JSONSerialization.data(withJSONObject: [normalized])) ?? Data()
        let initialJSON: String
        if let jsonArray = String(data: jsonData, encoding: .utf8),
           let element = jsonArray.dropFirst().dropLast().trimmingCharacters(in: .whitespaces).isEmpty ? nil : String(jsonArray.dropFirst().dropLast()) {
            initialJSON = element
        } else {
            initialJSON = "\"\""
        }

        return """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
          <style>
            \(cachedCSS)
            
            :root {
              color-scheme: dark;
            }
            * {
              box-sizing: border-box;
              -webkit-tap-highlight-color: transparent;
            }
            html, body {
              margin: 0;
              padding: 0;
              background-color: transparent !important;
              color: rgba(255, 255, 255, 0.92);
              font-family: Georgia, "Times New Roman", serif;
              font-size: 16px;
              line-height: 1.6;
              -webkit-font-smoothing: antialiased;
              word-break: break-word;
              overflow-wrap: break-word;
              overflow-y: hidden;
            }
            p {
              margin: 0.5em 0;
            }
            p:first-child {
              margin-top: 0;
            }
            p:last-child {
              margin-bottom: 0;
            }
            h1, h2, h3, h4 {
              color: #FFFFFF;
              margin: 0.8em 0 0.3em 0;
              font-weight: 600;
            }
            h1 { font-size: 1.4em; }
            h2 { font-size: 1.25em; }
            h3 { font-size: 1.1em; }
            h4 { font-size: 1.0em; }
            
            /* Horizontal scroll for wide block equations on mobile viewports */
            .katex-display {
              overflow-x: auto;
              overflow-y: hidden;
              padding: 0.75rem 0;
              margin: 0.5rem 0;
              -webkit-overflow-scrolling: touch;
            }
            
            /* Keep inline equations from wrapping mid-expression */
            .katex {
              font-size: 1.05em;
              white-space: nowrap;
            }
            
            /* Allow inline math inside tables to wrap cleanly if needed */
            td .katex,
            th .katex {
              white-space: normal;
            }
            
            /* Style \\boxed{} borders for dark mode UI */
            .katex .boxpad {
              border-color: rgba(255, 255, 255, 0.35);
              padding: 0.4em;
            }
            
            /* Markdown Tables (Phase 4 / GFM table parity) */
            .table-container {
              width: 100%;
              overflow-x: auto;
              -webkit-overflow-scrolling: touch;
              margin: 0.8em 0;
            }
            table {
              border-collapse: collapse;
              width: 100%;
              border-radius: 8px;
              border: 1px solid rgba(200, 184, 150, 0.35);
              background-color: #1A1A1E;
              overflow: hidden;
            }
            th {
              background-color: rgba(255, 255, 255, 0.06);
              color: #FFFFFF;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              font-size: 13.5px;
              font-weight: 600;
              padding: 10px 14px;
              text-align: left;
              border-bottom: 1.5px solid rgba(200, 184, 150, 0.40);
              border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
            th:last-child {
              border-right: none;
            }
            td {
              padding: 9px 14px;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              font-size: 13px;
              color: #ECECEE;
              border-bottom: 1px solid rgba(255, 255, 255, 0.06);
              border-right: 1px solid rgba(255, 255, 255, 0.06);
            }
            td:last-child {
              border-right: none;
            }
            tr:nth-child(even) td {
              background-color: rgba(255, 255, 255, 0.025);
            }
            tr:last-child td {
              border-bottom: none;
            }
            
            /* Code blocks & Pre */
            pre {
              background: rgba(255, 255, 255, 0.035);
              border: 1px solid rgba(255, 255, 255, 0.08);
              border-radius: 8px;
              padding: 12px;
              overflow-x: auto;
              font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
              font-size: 13px;
            }
            code {
              font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
              font-size: 0.9em;
              background: rgba(255, 255, 255, 0.06);
              padding: 2px 5px;
              border-radius: 4px;
            }
            pre code {
              background: transparent;
              padding: 0;
            }
            
            /* Lists */
            ul, ol {
              padding-left: 20px;
              margin: 0.5em 0;
            }
            li {
              margin: 0.25em 0;
            }
            
            /* Blockquotes */
            blockquote {
              margin: 0.6em 0;
              padding: 4px 0 4px 12px;
              border-left: 3px solid #C8B896;
              color: rgba(255, 255, 255, 0.88);
            }
            
            /* Links */
            a {
              color: #C8B896;
              text-decoration: underline;
            }
          </style>
          <script>
            \(cachedKaTeXJS)
          </script>
          <script>
            \(cachedMarkedJS)
          </script>
        </head>
        <body>
          <div id="content"></div>
          <script>
            function renderSafeMathMarkdown(markdown) {
              if (!markdown) return "";
              const placeholders = [];
              
              // 1. Extract block equations $$...$$
              let text = markdown.replace(/\\$\\$([\\s\\S]*?)\\$\\$/g, function(match, equation) {
                const idx = placeholders.length;
                let rendered = "";
                try {
                  rendered = katex.renderToString(equation.trim(), { displayMode: true, throwOnError: false });
                } catch (e) {
                  rendered = '<div class="katex-display">' + equation + '</div>';
                }
                placeholders.push(rendered);
                return '%%%MATH_PLACEHOLDER_' + idx + '%%%';
              });

              // 2. Extract inline equations $...$
              text = text.replace(/\\$([^\\$\\n]+?)\\$/g, function(match, equation) {
                const idx = placeholders.length;
                let rendered = "";
                try {
                  rendered = katex.renderToString(equation.trim(), { displayMode: false, throwOnError: false });
                } catch (e) {
                  rendered = '<span class="katex">' + equation + '</span>';
                }
                placeholders.push(rendered);
                return '%%%MATH_PLACEHOLDER_' + idx + '%%%';
              });

              // 2.5. Extract bare \\boxed{...} that were not enclosed inside $$ or $
              text = text.replace(/\\\\boxed\\{([^{}]*(?:\\{[^{}]*\\}[^{}]*)*)\\}/g, function(match, equation) {
                const idx = placeholders.length;
                let rendered = "";
                try {
                  rendered = katex.renderToString('\\\\boxed{' + equation.trim() + '}', { displayMode: true, throwOnError: false });
                } catch (e) {
                  rendered = '<div class="katex-display">\\\\boxed{' + equation + '}</div>';
                }
                placeholders.push(rendered);
                return '%%%MATH_PLACEHOLDER_' + idx + '%%%';
              });

              // 3. Marked GFM Parser
              if (window.marked) {
                marked.setOptions({ gfm: true, breaks: true });
                text = marked.parse(text);
              }

              // 4. Wrap tables in scrollable container
              text = text.replace(/<table>/g, '<div class="table-container"><table>').replace(/<\\/table>/g, '</table></div>');

              // 5. Restore Math placeholders
              text = text.replace(/%%%MATH_PLACEHOLDER_(\\d+)%%%/g, function(match, id) {
                const idx = parseInt(id, 10);
                return placeholders[idx] !== undefined ? placeholders[idx] : match;
              });

              return text;
            }

            function notifyHeight() {
              const container = document.getElementById('content');
              const h = Math.ceil(Math.max(
                container ? container.scrollHeight : 0,
                container ? container.offsetHeight : 0,
                document.body.scrollHeight,
                document.documentElement.scrollHeight,
                40
              ));
              if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.heightHandler) {
                window.webkit.messageHandlers.heightHandler.postMessage(h);
              }
            }

            window.updateContent = function(markdown) {
              document.getElementById('content').innerHTML = renderSafeMathMarkdown(markdown);
              requestAnimationFrame(function() {
                notifyHeight();
                setTimeout(notifyHeight, 80);
              });
            };

            // Render initial content immediately
            const initMarkdown = \(initialJSON);
            if (initMarkdown) {
              window.updateContent(initMarkdown);
            }

            window.addEventListener('load', notifyHeight);
            window.addEventListener('resize', notifyHeight);
          </script>
        </body>
        </html>
        """
    }
}
