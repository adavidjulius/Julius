import SwiftUI
import JuliusCore

#if os(macOS)
import AppKit

public struct ScrollableTextInputView: NSViewRepresentable {
    @Binding public var text: String
    @Binding public var dynamicHeight: CGFloat
    public let placeholder: String
    public let minHeight: CGFloat
    public let maxHeight: CGFloat
    public let onSend: () -> Void

    public init(
        text: Binding<String>,
        dynamicHeight: Binding<CGFloat> = .constant(28),
        placeholder: String = "Ask Julius...",
        minHeight: CGFloat = 28,
        maxHeight: CGFloat = 135,
        onSend: @escaping () -> Void
    ) {
        self._text = text
        self._dynamicHeight = dynamicHeight
        self.placeholder = placeholder
        self.minHeight = minHeight
        self.maxHeight = maxHeight
        self.onSend = onSend
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    public func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true

        let textView = CommandTextView()
        textView.minSize = NSSize(width: 0, height: minHeight)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.containerSize = NSSize(width: 380, height: CGFloat.greatestFiniteMagnitude)
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.lineFragmentPadding = 0
        textView.textContainerInset = NSSize(width: 0, height: 4)
        textView.drawsBackground = false
        textView.backgroundColor = .clear
        textView.textColor = NSColor(red: 0.96, green: 0.96, blue: 0.97, alpha: 1.0)
        textView.font = NSFont.systemFont(ofSize: 15.5, weight: .regular)
        textView.insertionPointColor = NSColor(red: 0.784, green: 0.722, blue: 0.588, alpha: 1.0) // Brand Gold #C8B896
        textView.delegate = context.coordinator
        textView.isRichText = false
        textView.allowsUndo = true
        textView.string = text

        textView.onReturnPressed = {
            context.coordinator.parent.onSend()
        }

        scrollView.documentView = textView
        context.coordinator.textView = textView
        context.coordinator.scrollView = scrollView
        context.coordinator.updateHeight(for: textView)

        return scrollView
    }

    public func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
        let width = proposal.width ?? 380
        guard let tv = nsView.documentView as? NSTextView else {
            return CGSize(width: width, height: minHeight)
        }
        if tv.string.isEmpty {
            return CGSize(width: width, height: minHeight)
        }
        let lineCount = tv.string.components(separatedBy: "\n").count
        let estimatedHeight = CGFloat(max(1, lineCount)) * 21.0 + 4.0
        let clamped = min(max(minHeight, estimatedHeight), maxHeight)
        return CGSize(width: width, height: clamped)
    }

    public func updateNSView(_ nsView: NSScrollView, context: Context) {
        guard let textView = nsView.documentView as? CommandTextView else { return }
        if textView.string != text {
            let selectedRanges = textView.selectedRanges
            textView.string = text
            textView.selectedRanges = selectedRanges
            context.coordinator.updateHeight(for: textView)
        }
    }

    @MainActor
    public final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ScrollableTextInputView
        weak var textView: CommandTextView?
        weak var scrollView: NSScrollView?

        init(_ parent: ScrollableTextInputView) {
            self.parent = parent
        }

        public func textDidChange(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            let newText = tv.string
            if self.parent.text != newText {
                self.parent.text = newText
            }
            updateHeight(for: tv)
            tv.scrollRangeToVisible(tv.selectedRange())
        }

        func updateHeight(for tv: NSTextView) {
            if tv.string.isEmpty {
                if abs(parent.dynamicHeight - parent.minHeight) > 0.5 {
                    DispatchQueue.main.async {
                        self.parent.dynamicHeight = self.parent.minHeight
                    }
                }
                return
            }

            let lineCount = tv.string.components(separatedBy: "\n").count
            let fallbackHeight = CGFloat(max(1, lineCount)) * 21.0

            let usedHeight: CGFloat
            if let layoutManager = tv.layoutManager, let textContainer = tv.textContainer {
                layoutManager.ensureLayout(for: textContainer)
                usedHeight = layoutManager.usedRect(for: textContainer).height
            } else {
                usedHeight = fallbackHeight
            }

            let actualHeight = max(usedHeight, fallbackHeight)
            let contentHeight = max(parent.minHeight, actualHeight + 6)
            let clamped = min(parent.maxHeight, contentHeight)

            if abs(parent.dynamicHeight - clamped) > 1.0 {
                DispatchQueue.main.async {
                    self.parent.dynamicHeight = clamped
                }
            }
        }
    }
}

final class CommandTextView: NSTextView {
    var onReturnPressed: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        // Return without shift = send
        if event.keyCode == 36 { // Return key
            if event.modifierFlags.contains(.shift) || event.modifierFlags.contains(.option) {
                super.insertNewline(nil)
                return
            }
            if let onSend = onReturnPressed {
                let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    onSend()
                    return
                }
            }
        }
        super.keyDown(with: event)
    }
}

#else

public struct ScrollableTextInputView: View {
    @Binding public var text: String
    @Binding public var dynamicHeight: CGFloat
    public let placeholder: String
    public let minHeight: CGFloat
    public let maxHeight: CGFloat
    public let onSend: () -> Void

    public init(
        text: Binding<String>,
        dynamicHeight: Binding<CGFloat> = .constant(28),
        placeholder: String = "Ask Julius...",
        minHeight: CGFloat = 28,
        maxHeight: CGFloat = 135,
        onSend: @escaping () -> Void
    ) {
        self._text = text
        self._dynamicHeight = dynamicHeight
        self.placeholder = placeholder
        self.minHeight = minHeight
        self.maxHeight = maxHeight
        self.onSend = onSend
    }

    public var body: some View {
        if #available(iOS 16.0, *) {
            TextField(placeholder, text: $text, axis: .vertical)
                .lineLimit(1...5)
                .font(.system(size: 15.5))
                .foregroundColor(.white)
                .submitLabel(.send)
                .onSubmit {
                    onSend()
                }
        } else {
            TextEditor(text: $text)
                .font(.system(size: 15.5))
                .foregroundColor(.white)
                .scrollContentBackground(.hidden)
                .frame(height: dynamicHeight)
        }
    }
}

#endif
