#pragma once

#include <windows.h>
#include <dwmapi.h>

#include "tip_logic.h"

// The candidate list and the one-line notice share the same GDI surface.
class TipPopup {
public:
    struct Row { std::wstring text, note; };

    explicit TipPopup(bool notice = false) : notice_(notice) {}
    ~TipPopup() { Destroy(); }
    TipPopup(const TipPopup&) = delete;
    TipPopup& operator=(const TipPopup&) = delete;

    HWND Window() const { return hwnd_; }
    bool HasRows() const { return !rows_.empty(); }

    void SetRows(std::vector<Row> rows, int selected = -1, std::wstring footer = {},
                 bool numbered = true) {
        rows_ = std::move(rows);
        selected_ = selected;
        footer_ = std::move(footer);
        numbered_ = numbered;
        layout_dirty_ = true;
    }

    void Hide() {
        if (hwnd_) ShowWindow(hwnd_, SW_HIDE);
    }

    void Clear() {
        Hide();
        SetRows({});
    }

    void Destroy() {
        if (hwnd_) DestroyWindow(hwnd_);
        hwnd_ = nullptr;
        Clear();
        if (text_font_) DeleteObject(text_font_);
        if (small_font_) DeleteObject(small_font_);
        text_font_ = small_font_ = nullptr;
        dpi_ = 0;
    }

    bool Place(const RECT& caret, HINSTANCE instance) {
        if (!HasRows()) return false;
        HMONITOR monitor = MonitorFromRect(&caret, MONITOR_DEFAULTTONEAREST);
        MONITORINFO info{sizeof(info)};
        if (!GetMonitorInfoW(monitor, &info)) return false;
        caret_ = caret;
        work_ = info.rcWork;
        if (!hwnd_ && !Create(instance)) return false;
        if (MonitorFromWindow(hwnd_, MONITOR_DEFAULTTONEAREST) != monitor) {
            // Move into the new monitor before measuring, in the host's DPI awareness mode.
            changing_monitor_ = true;
            SetWindowPos(hwnd_, nullptr, caret.left, caret.top, 1, 1,
                         SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOREDRAW);
            changing_monitor_ = false;
            layout_dirty_ = true;
        }
        return Position(GetDpiForWindow(hwnd_), SWP_SHOWWINDOW);
    }

private:
    static constexpr UINT kTextFlags = DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | DT_END_ELLIPSIS;

    bool Create(HINSTANCE instance) {
        WNDCLASSW wc{};
        wc.lpfnWndProc = WindowProc;
        wc.hInstance = instance;
        wc.lpszClassName = L"YuragiPopup";
        RegisterClassW(&wc);
        hwnd_ = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_TRANSPARENT,
                                wc.lpszClassName, L"", WS_POPUP | WS_THICKFRAME,
                                caret_.left, caret_.top, 1, 1, nullptr, nullptr, instance, this);
        if (!hwnd_) return false;
        const DWM_WINDOW_CORNER_PREFERENCE corners = DWMWCP_ROUND;
        DwmSetWindowAttribute(hwnd_, DWMWA_WINDOW_CORNER_PREFERENCE, &corners, sizeof(corners));
        const BOOL disable_transitions = TRUE;
        DwmSetWindowAttribute(hwnd_, DWMWA_TRANSITIONS_FORCEDISABLED,
                              &disable_transitions, sizeof(disable_transitions));
        // The frame style gives DWM a shadow. The client paints the visible border.
        const COLORREF border = DWMWA_COLOR_NONE;
        DwmSetWindowAttribute(hwnd_, DWMWA_BORDER_COLOR, &border, sizeof(border));
        RefreshColors();
        return true;
    }

    void RefreshColors() {
        HIGHCONTRASTW contrast{sizeof(contrast)};
        std::optional<tip_logic::PopupColors> system;
        if (SystemParametersInfoW(SPI_GETHIGHCONTRAST, sizeof(contrast), &contrast, 0) &&
            (contrast.dwFlags & HCF_HIGHCONTRASTON)) {
            system = tip_logic::PopupColors{GetSysColor(COLOR_WINDOW), GetSysColor(COLOR_WINDOWTEXT),
                GetSysColor(COLOR_WINDOWTEXT), GetSysColor(COLOR_WINDOWTEXT), GetSysColor(COLOR_HIGHLIGHT),
                GetSysColor(COLOR_HIGHLIGHTTEXT), GetSysColor(COLOR_HIGHLIGHTTEXT)};
        }
        DWORD light = 1;
        DWORD size = sizeof(light);
        const bool dark = !system && RegGetValueW(HKEY_CURRENT_USER,
            L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
            L"AppsUseLightTheme", RRF_RT_REG_DWORD, nullptr, &light, &size) == ERROR_SUCCESS && !light;
        DWORD argb;
        BOOL opaque;
        COLORREF accent = GetSysColor(COLOR_HIGHLIGHT);
        if (!system && SUCCEEDED(DwmGetColorizationColor(&argb, &opaque)))
            accent = RGB((argb >> 16) & 255, (argb >> 8) & 255, argb & 255);
        colors_ = tip_logic::PopupPalette(dark, accent, system);
        const BOOL immersive_dark = dark;
        DwmSetWindowAttribute(hwnd_, DWMWA_USE_IMMERSIVE_DARK_MODE, &immersive_dark, sizeof(immersive_dark));
        InvalidateRect(hwnd_, nullptr, FALSE);
    }

    static HFONT MakeFont(int height) {
        return CreateFontW(-height, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, SHIFTJIS_CHARSET,
                           OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                           DEFAULT_PITCH, L"Yu Gothic UI");
    }

    static void SelectFont(HDC dc, HFONT font) {
        SelectObject(dc, font ? font : GetStockObject(DEFAULT_GUI_FONT));
    }

    static int TextWidth(HDC dc, const std::wstring& text) {
        SIZE size{};
        if (!text.empty()) GetTextExtentPoint32W(dc, text.c_str(), (int)text.size(), &size);
        return size.cx;
    }

    bool Position(UINT dpi, UINT flags) {
        if (!dpi) dpi = 96;
        if (dpi != dpi_) {
            dpi_ = dpi;
            metrics_ = tip_logic::ScalePopup(dpi);
            if (text_font_) DeleteObject(text_font_);
            if (small_font_) DeleteObject(small_font_);
            text_font_ = MakeFont(metrics_.text_font);
            small_font_ = MakeFont(metrics_.small_font);
            layout_dirty_ = true;
        }
        const int work_width = work_.right - work_.left;
        const bool measure = layout_dirty_ || work_width != measured_work_width_;
        if (measure) {
            HDC dc = GetDC(hwnd_);
            if (!dc) return false;
            int text = 0, notes = 0;
            SelectFont(dc, notice_ ? small_font_ : text_font_);
            for (const auto& row : rows_) text = std::max(text, TextWidth(dc, row.text));
            SelectFont(dc, small_font_);
            for (const auto& row : rows_) notes = std::max(notes, TextWidth(dc, row.note));
            layout_ = tip_logic::MeasurePopup(metrics_, work_width, (int)rows_.size(), selected_,
                                              text, notes, TextWidth(dc, footer_), notice_, numbered_);
            ReleaseDC(hwnd_, dc);
            measured_work_width_ = work_width;
            layout_dirty_ = false;
        }
        int x = std::clamp((int)caret_.left, (int)work_.left, (int)work_.right - layout_.width);
        int y = tip_logic::CandidateTop(caret_.top, caret_.bottom, layout_.height,
                                       metrics_.gap, work_.bottom);
        y = std::clamp(y, (int)work_.top, std::max((int)work_.top, (int)work_.bottom - layout_.height));
        if (!SetWindowPos(hwnd_, HWND_TOPMOST, x, y, layout_.width, layout_.height,
                          SWP_NOACTIVATE | flags)) return false;
        if (measure) InvalidateRect(hwnd_, nullptr, FALSE);
        return true;
    }

    static void Fill(HDC dc, const RECT& rect, COLORREF color) {
        SetDCBrushColor(dc, color);
        FillRect(dc, &rect, (HBRUSH)GetStockObject(DC_BRUSH));
    }

    static void Text(HDC dc, const std::wstring& text, RECT rect, COLORREF color, UINT flags = 0) {
        if (text.empty() || rect.right <= rect.left) return;
        SetTextColor(dc, color);
        DrawTextW(dc, text.c_str(), (int)text.size(), &rect, kTextFlags | flags);
    }

    void Draw(HDC dc, const RECT& client) const {
        Fill(dc, client, colors_.surface);
        SetDCBrushColor(dc, colors_.border);
        FrameRect(dc, &client, (HBRUSH)GetStockObject(DC_BRUSH));
        SetBkMode(dc, TRANSPARENT);
        SelectObject(dc, GetStockObject(DC_BRUSH));
        SelectObject(dc, GetStockObject(NULL_PEN));
        for (int i = 0; i < layout_.rows && i < (int)rows_.size(); ++i) {
            const auto row = layout_.Row(metrics_, i);
            const bool selected = i == layout_.selected;
            if (selected) {
                SetDCBrushColor(dc, colors_.selected);
                RoundRect(dc, row.left, row.top + 1, row.right, row.bottom - 1,
                          metrics_.rounding, metrics_.rounding);
                const int top = (row.top + row.bottom - metrics_.mark_height) / 2;
                SetDCBrushColor(dc, colors_.mark);
                RoundRect(dc, row.left + 1, top, row.left + 1 + metrics_.mark_width,
                          top + metrics_.mark_height, metrics_.mark_width, metrics_.mark_width);
            }
            const COLORREF secondary = selected && colors_.selected_text != colors_.text
                                     ? colors_.selected_text : colors_.secondary;
            SelectFont(dc, small_font_);
            if (!notice_ && numbered_) {
                Text(dc, std::to_wstring(i + 1), {row.left + metrics_.padding, row.top,
                     layout_.text_left - metrics_.number_column / 2, row.bottom}, secondary, DT_RIGHT);
            }
            Text(dc, rows_[i].note, {layout_.note_left, row.top,
                 row.right - metrics_.padding, row.bottom}, secondary, DT_RIGHT);
            SelectFont(dc, notice_ ? small_font_ : text_font_);
            Text(dc, rows_[i].text, {layout_.text_left, row.top, layout_.text_right, row.bottom},
                 selected ? colors_.selected_text : colors_.text);
        }
        if (!footer_.empty() && layout_.height > layout_.footer_top) {
            const int right = layout_.width - metrics_.inset;
            Fill(dc, {metrics_.inset, layout_.footer_top, right, layout_.footer_top + 1}, colors_.border);
            SelectFont(dc, small_font_);
            Text(dc, footer_, {metrics_.inset + metrics_.padding, layout_.footer_top,
                 right - metrics_.padding, layout_.height - 1}, colors_.secondary, DT_RIGHT);
        }
    }

    void Paint() const {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd_, &ps);
        RECT client{};
        GetClientRect(hwnd_, &client);
        HDC back = CreateCompatibleDC(dc);
        HBITMAP bitmap = back ? CreateCompatibleBitmap(dc, client.right, client.bottom) : nullptr;
        HGDIOBJ old = bitmap ? SelectObject(back, bitmap) : nullptr;
        if (old) {
            Draw(back, client);
            BitBlt(dc, 0, 0, client.right, client.bottom, back, 0, 0, SRCCOPY);
            SelectObject(back, old);
        } else {
            if (int saved = SaveDC(dc)) {
                Draw(dc, client);
                RestoreDC(dc, saved);
            }
        }
        if (back) DeleteDC(back);
        if (bitmap) DeleteObject(bitmap);
        EndPaint(hwnd_, &ps);
    }

    static LRESULT CALLBACK WindowProc(HWND h, UINT msg, WPARAM w, LPARAM l) {
        if (msg == WM_NCCREATE) {
            const auto* create = reinterpret_cast<const CREATESTRUCTW*>(l);
            SetWindowLongPtrW(h, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create->lpCreateParams));
        }
        switch (msg) {
            case WM_NCCALCSIZE: return 0;  // The client fills the DWM frame.
            case WM_ERASEBKGND: return 1;
            case WM_MOUSEACTIVATE: return MA_NOACTIVATE;
            case WM_NCHITTEST: return HTTRANSPARENT;
        }
        auto* self = reinterpret_cast<TipPopup*>(GetWindowLongPtrW(h, GWLP_USERDATA));
        if (self && self->hwnd_) {
            switch (msg) {
                case WM_NCDESTROY:
                    self->hwnd_ = nullptr;
                    self->layout_dirty_ = true;
                    break;
                case WM_PAINT:
                    self->Paint();
                    return 0;
                case WM_DPICHANGED:
                    if (!self->changing_monitor_ && IsWindowVisible(h)) {
                        MONITORINFO info{sizeof(info)};
                        if (GetMonitorInfoW(MonitorFromRect(&self->caret_, MONITOR_DEFAULTTONEAREST), &info))
                            self->work_ = info.rcWork;
                        self->Position(HIWORD(w), 0);
                    }
                    return 0;
                case WM_SETTINGCHANGE:
                case WM_SYSCOLORCHANGE:
                case WM_THEMECHANGED:
                case WM_DWMCOLORIZATIONCOLORCHANGED:
                    self->RefreshColors();
                    break;
            }
        }
        return DefWindowProcW(h, msg, w, l);
    }

    HWND hwnd_ = nullptr;
    HFONT text_font_ = nullptr, small_font_ = nullptr;
    UINT dpi_ = 0;
    tip_logic::PopupColors colors_{};
    tip_logic::PopupMetrics metrics_{};
    tip_logic::PopupLayout layout_{};
    RECT caret_{}, work_{};
    std::vector<Row> rows_;
    std::wstring footer_;
    bool numbered_ = true;
    int selected_ = -1, measured_work_width_ = 0;
    bool layout_dirty_ = true, changing_monitor_ = false;
    const bool notice_;
};
