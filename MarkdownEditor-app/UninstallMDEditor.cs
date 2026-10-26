// SPDX-License-Identifier: AGPL-3.0-or-later
// MDEditor uninstaller GUI. Compiled at packaging time by the system csc.exe
// (Windows built-in .NET Framework compiler). No third-party tools.
//
// Safety model (root-cause of the 2026-10-19 workspace-loss incident):
//   - uninstall.cmd NEVER deletes program files; it only clears registry
//     integration, shortcuts and the ARP entry. It is safe to run anywhere.
//   - File deletion happens ONLY here, opt-in via checkbox, with a second
//     explicit confirmation, and only after this GUI process exits.
//
// UI shares the installer's design language (installer/_setup_win.cs):
//   - same Palette (light/dark follows system theme), same header / status
//     strip / log groupbox layout;
//   - design coordinates are authored at 96 DPI and scaled at runtime by the
//     real per-monitor DPI (app.manifest declares PerMonitorV2), so the
//     window stays crisp at 125% / 150% instead of getting GDI-blurred;
//   - fonts come from the system UI font family, GB2312 charset enables font
//     linking so CJK text never falls back to bitmap SimSun.
//
// Compiled with: csc /target:winexe /win32manifest:app.manifest
//                    /win32icon:uninstall-md.ico UninstallMDEditor.cs
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace MDEditorUninstall
{
    class Palette
    {
        public Color Canvas;      // 窗体底色
        public Color Surface;     // 卡片 / 输入框底
        public Color Header;      // 顶栏底色
        public Color HeaderText;  // 顶栏主文字
        public Color HeaderSub;   // 顶栏次要文字
        public Color Text;        // 正文
        public Color TextDim;     // 次要正文
        public Color Border;      // 描边
        public Color Accent;      // 主按钮
        public Color AccentText;
        public Color Ok;          // 状态条：正常
        public Color Warn;        // 状态条：告警 / 危险
        public bool Dark;
    }

    static class Ui
    {
        internal static readonly Palette Light = new Palette
        {
            Canvas = Color.FromArgb(0xF1, 0xF4, 0xF8),
            Surface = Color.White,
            Header = Color.FromArgb(0x17, 0x26, 0x3F),
            HeaderText = Color.White,
            HeaderSub = Color.FromArgb(0xA6, 0xB6, 0xCD),
            Text = Color.FromArgb(0x1B, 0x24, 0x30),
            TextDim = Color.FromArgb(0x5C, 0x6A, 0x7C),
            Border = Color.FromArgb(0xD2, 0xDA, 0xE5),
            Accent = Color.FromArgb(0x2F, 0x6F, 0xEB),
            AccentText = Color.White,
            Ok = Color.FromArgb(0x1B, 0x8A, 0x4B),
            Warn = Color.FromArgb(0xB5, 0x6A, 0x11),
            Dark = false
        };

        internal static readonly Palette Dark = new Palette
        {
            Canvas = Color.FromArgb(0x15, 0x1A, 0x21),
            Surface = Color.FromArgb(0x1D, 0x24, 0x2E),
            Header = Color.FromArgb(0x0C, 0x11, 0x18),
            HeaderText = Color.FromArgb(0xEC, 0xF1, 0xF7),
            HeaderSub = Color.FromArgb(0x93, 0xA3, 0xB6),
            Text = Color.FromArgb(0xE3, 0xE9, 0xF0),
            TextDim = Color.FromArgb(0x9B, 0xA8, 0xB8),
            Border = Color.FromArgb(0x30, 0x3A, 0x47),
            Accent = Color.FromArgb(0x4C, 0x8D, 0xFF),
            AccentText = Color.FromArgb(0x0C, 0x11, 0x18),
            Ok = Color.FromArgb(0x4C, 0xC3, 0x8C),
            Warn = Color.FromArgb(0xE0, 0xA9, 0x55),
            Dark = true
        };

        internal static Palette Current { get; private set; }

        internal static void Init()
        {
            bool dark = false;
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                {
                    object v = k == null ? null : k.GetValue("AppsUseLightTheme");
                    if (v != null) dark = Convert.ToInt32(v) == 0;
                }
            }
            catch { }
            Current = dark ? Dark : Light;
        }

        // 与安装器同一套：系统 UI 字体族 + GB2312 字符集激活字体链接。
        internal static Font FontOf(float size, FontStyle style)
        {
            return new Font(SystemFonts.MessageBoxFont.FontFamily, size, style,
                            GraphicsUnit.Point, 134);
        }

        internal static Font MonoFontOf(float size)
        {
            return new Font(FontFamily.GenericMonospace, size, FontStyle.Regular,
                            GraphicsUnit.Point, 134);
        }
    }

    class UninstallForm : Form
    {
        const int WM_DPICHANGED = 0x02E0;

        [StructLayout(LayoutKind.Sequential)]
        struct RECT { public int Left, Top, Right, Bottom; }

        [DllImport("user32.dll")]
        static extern uint GetDpiForWindow(IntPtr hwnd);
        [DllImport("user32.dll")]
        static extern uint GetDpiForSystem();
        [DllImport("user32.dll")]
        static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref uint val, int size);

        // 设计稿坐标一律按 96 DPI 写，运行期按实际 DPI 换算。
        readonly Dictionary<Control, Rectangle> _design = new Dictionary<Control, Rectangle>();

        readonly Label _lblDir = new Label();
        readonly TextBox _txtDir = new TextBox();
        readonly TextBox _txtLog = new TextBox();
        readonly Button _btnGo = new Button();
        readonly Button _btnCancel = new Button();
        readonly Label _lblStatus = new Label();
        readonly Label _lblTitle = new Label();
        readonly Label _lblSub = new Label();
        readonly Label _lblDesc = new Label();
        readonly Panel _pnlHeader = new Panel();
        readonly Panel _pnlStatus = new Panel();
        readonly Panel _pnlDot = new Panel();
        readonly PictureBox _picIcon = new PictureBox();
        readonly GroupBox _grpLog = new GroupBox();
        readonly ProgressBar _prog = new ProgressBar();
        CheckBox _chk;
        bool _running;
        bool _done;
        float _k = 1f;

        public UninstallForm()
        {
            Ui.Init();
            var pal = Ui.Current;

            string dir = AppDomain.CurrentDomain.BaseDirectory;

            Text = "卸载 MDEditor";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false;
            MinimizeBox = false;
            AutoScaleMode = AutoScaleMode.None;   // 缩放由本类自己按 DPI 精确控制
            ClientSize = new Size(560, 470);
            BackColor = pal.Canvas;
            ForeColor = pal.Text;
            Font = Ui.FontOf(9f, FontStyle.Regular);

            try
            {
                var ico = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (ico != null) _picIcon.Image = ico.ToBitmap();
            }
            catch { }

            // ---- 顶栏 ----
            _pnlHeader.BackColor = pal.Header;
            Put(_pnlHeader, 0, 0, 560, 76);
            _picIcon.SizeMode = PictureBoxSizeMode.StretchImage;
            Put(_picIcon, 24, 22, 32, 32);
            _lblTitle.Text = "MDEditor";
            _lblTitle.Font = Ui.FontOf(15f, FontStyle.Bold);
            _lblTitle.ForeColor = pal.HeaderText;
            _lblTitle.BackColor = Color.Transparent;
            Put(_lblTitle, 72, 16, 320, 28);
            _lblSub.Text = "卸载程序";
            _lblSub.Font = Ui.FontOf(9f, FontStyle.Regular);
            _lblSub.ForeColor = pal.HeaderSub;
            _lblSub.BackColor = Color.Transparent;
            Put(_lblSub, 74, 44, 320, 20);
            _pnlHeader.Controls.Add(_picIcon);
            _pnlHeader.Controls.Add(_lblTitle);
            _pnlHeader.Controls.Add(_lblSub);

            // ---- 安装目录（只读、可复制） ----
            _lblDir.Text = "安装目录：";
            _lblDir.ForeColor = pal.Text;
            Put(_lblDir, 20, 92, 72, 22);
            _txtDir.Text = dir;
            _txtDir.ReadOnly = true;
            _txtDir.Font = Ui.FontOf(9f, FontStyle.Regular);
            _txtDir.BorderStyle = BorderStyle.FixedSingle;
            _txtDir.BackColor = pal.Surface;
            _txtDir.ForeColor = pal.Text;
            // TextBox 拿到焦点会自动全选，收掉，避免深蓝选区像被误触。
            _txtDir.HandleCreated += (s, e) =>
            {
                _txtDir.SelectionLength = 0;
                _txtDir.SelectionStart = _txtDir.TextLength;
            };
            Put(_txtDir, 96, 89, 444, 26);

            // ---- 状态条 ----
            bool hasCmd = File.Exists(Path.Combine(dir, "uninstall.cmd"));
            _pnlStatus.BackColor = pal.Surface;
            Put(_pnlStatus, 20, 128, 520, 38);
            _pnlDot.BackColor = hasCmd ? pal.Ok : pal.Warn;
            Put(_pnlDot, 0, 0, 4, 38);
            _lblStatus.Text = hasCmd
                ? "已定位本机安装，将清除系统集成与快捷方式，程序文件默认保留"
                : "未找到 uninstall.cmd：集成项无法自动清除，建议保留文件手动清理";
            _lblStatus.ForeColor = pal.TextDim;
            _lblStatus.TextAlign = ContentAlignment.MiddleLeft;
            Put(_lblStatus, 16, 0, 492, 38);
            _pnlStatus.Controls.Add(_pnlDot);
            _pnlStatus.Controls.Add(_lblStatus);

            // ---- 说明 ----
            _lblDesc.Text = "卸载将清除：.md/.smd 右键菜单与文件关联、桌面/开始菜单快捷方式、" +
                            "「设置 → 应用」卸载条目，并停止运行中的后台服务。\n" +
                            "程序文件默认保留，可随时重新安装或继续绿色使用。";
            _lblDesc.ForeColor = pal.TextDim;
            Put(_lblDesc, 22, 180, 516, 56);

            // ---- 删除文件选项 ----
            _chk = new CheckBox
            {
                Text = "同时删除程序文件（不可恢复）",
                ForeColor = pal.Text,
                FlatStyle = FlatStyle.System
            };
            Put(_chk, 22, 244, 516, 24);
            _chk.CheckedChanged += (s, e) =>
            {
                _chk.ForeColor = _chk.Checked ? pal.Warn : pal.Text;
            };

            // ---- 日志区 ----
            _grpLog.Text = "卸载日志";
            _grpLog.ForeColor = pal.TextDim;
            _grpLog.BackColor = pal.Canvas;
            Put(_grpLog, 20, 276, 520, 140);
            _txtLog.Multiline = true;
            _txtLog.ReadOnly = true;
            _txtLog.ScrollBars = ScrollBars.Vertical;
            _txtLog.BackColor = pal.Surface;
            _txtLog.ForeColor = pal.Text;
            // GroupBox 自带边框，内部文本框不再画一层，避免双框嵌套。
            _txtLog.BorderStyle = BorderStyle.None;
            _txtLog.Font = Ui.MonoFontOf(9f);
            Put(_txtLog, 10, 22, 504, 108);
            _grpLog.Controls.Add(_txtLog);

            // ---- 底部操作 ----
            _prog.Style = ProgressBarStyle.Marquee;
            _prog.MarqueeAnimationSpeed = 30;
            _prog.Visible = false;
            Put(_prog, 20, 428, 280, 24);
            _btnCancel.Text = "取消";
            StyleSecondary(_btnCancel, pal);
            Put(_btnCancel, 312, 426, 112, 32);
            _btnCancel.Click += (s, e) => Close();
            _btnGo.Text = "开始卸载";
            StylePrimary(_btnGo, pal);
            Put(_btnGo, 434, 426, 106, 32);
            _btnGo.Click += (s, e) => Go(dir);

            Controls.AddRange(new Control[] {
                _pnlHeader, _lblDir, _txtDir, _pnlStatus, _lblDesc, _chk,
                _grpLog, _prog, _btnCancel, _btnGo
            });
            AcceptButton = _btnGo;
            CancelButton = _btnCancel;

            ApplyScale(ScaleFactor());
        }

        static void StylePrimary(Button b, Palette pal)
        {
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 0;
            b.UseVisualStyleBackColor = false;
            b.BackColor = pal.Accent;
            b.ForeColor = pal.AccentText;
            b.Font = Ui.FontOf(9.5f, FontStyle.Bold);
            b.Cursor = Cursors.Hand;
        }

        static void StyleSecondary(Button b, Palette pal)
        {
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 1;
            b.FlatAppearance.BorderColor = pal.Border;
            b.UseVisualStyleBackColor = false;
            b.BackColor = pal.Surface;
            b.ForeColor = pal.Text;
            b.Cursor = Cursors.Hand;
        }

        // 记录设计稿坐标（相对父容器），缩放时按实际 DPI 重新换算。
        void Put(Control c, int x, int y, int w, int h)
        {
            _design[c] = new Rectangle(x, y, w, h);
            c.Location = new Point(x, y);
            c.Size = new Size(w, h);
        }

        static float ScaleFactor()
        {
            try
            {
                uint dpi = GetDpiForSystem();
                if (dpi >= 96) return dpi / 96f;
            }
            catch { }
            return 1f;
        }

        void ApplyScale(float k)
        {
            _k = k;
            foreach (var kv in _design)
            {
                var r = kv.Value;
                kv.Key.Location = new Point((int)Math.Round(r.X * k), (int)Math.Round(r.Y * k));
                kv.Key.Size = new Size((int)Math.Round(r.Width * k), (int)Math.Round(r.Height * k));
            }
            ClientSize = new Size((int)Math.Round(560 * k), (int)Math.Round(470 * k));
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            try
            {
                uint dpi = GetDpiForWindow(Handle);
                if (dpi >= 96) ApplyScale(dpi / 96f);
            }
            catch { }
            ApplyTitleBarStyle();
        }

        // 与安装器同一套标题栏处理：跟随深浅色，Win11 上直接染成顶栏色。
        void ApplyTitleBarStyle()
        {
            var pal = Ui.Current;
            try
            {
                int dark = pal.Dark ? 1 : 0;
                uint darkU = (uint)dark;
                DwmSetWindowAttribute(Handle, 20, ref darkU, 4);
                DwmSetWindowAttribute(Handle, 19, ref darkU, 4);
            }
            catch { }
            try
            {
                // COLORREF 打包值是 0x00BBGGRR（红在最低字节）。
                uint cap = ColorRef(pal.Header);
                uint txt = ColorRef(pal.HeaderText);
                DwmSetWindowAttribute(Handle, 35, ref cap, 4);
                DwmSetWindowAttribute(Handle, 36, ref txt, 4);
            }
            catch { }
        }

        static uint ColorRef(Color c)
        {
            return (uint)(c.B << 16 | c.G << 8 | c.R);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WM_DPICHANGED)
            {
                int dpi = (int)(m.WParam.ToInt64() & 0xFFFF);
                if (dpi >= 96)
                {
                    ApplyScale(dpi / 96f);
                    var r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                    SetWindowPos(Handle, IntPtr.Zero, r.Left, r.Top,
                                 r.Right - r.Left, r.Bottom - r.Top, 0x0004 /*SWP_NOZORDER*/);
                }
                return;
            }
            base.WndProc(ref m);
        }

        void Log(string msg)
        {
            if (_txtLog.InvokeRequired) { _txtLog.BeginInvoke((Action)(() => Log(msg))); return; }
            _txtLog.AppendText(msg + Environment.NewLine);
        }

        void Go(string dir)
        {
            if (_running || _done) return;
            if (MessageBox.Show("开始卸载 MDEditor？（程序文件默认保留）",
                "确认", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK)
                return;
            bool delFiles = _chk.Checked;
            _running = true;
            _btnGo.Enabled = false;
            _btnCancel.Enabled = false;
            _chk.Enabled = false;
            _prog.Visible = true;
            ThreadPool.QueueUserWorkItem(_ => RunUninstall(dir, delFiles));
        }

        // 后台线程执行：清理阶段界面保持可响应，跑马灯进度条指示进行中。
        void RunUninstall(string dir, bool delFiles)
        {
            try
            {
                var cmd = Path.Combine(dir, "uninstall.cmd");
                if (File.Exists(cmd))
                {
                    Log("清除注册表集成 / 快捷方式 / 卸载条目 ...");
                    var psi = new ProcessStartInfo("cmd.exe", "/c \"" + cmd + "\" nopause")
                    {
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        WorkingDirectory = Path.GetTempPath()
                    };
                    var p = Process.Start(psi);
                    if (!p.WaitForExit(120000)) Log("[!] uninstall.cmd 超时（部分集成项可能未清完）");
                    else Log("uninstall.cmd 完成（退出码 " + p.ExitCode + "）。");
                }
                else
                {
                    Log("[!] 未找到 uninstall.cmd，跳过系统集成清理。");
                }
            }
            catch (Exception ex)
            {
                Log("[!] " + ex.Message);
            }

            if (delFiles)
            {
                bool ok = false;
                Invoke((Action)(() =>
                {
                    ok = MessageBox.Show(this,
                        "将永久删除程序目录及其全部文件：\n\n" + dir +
                        "\n\n此操作不可恢复，确认删除？",
                        "二次确认", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning)
                        == DialogResult.OK;
                }));
                if (ok)
                {
                    Log("删除程序文件 ...");
                    SpawnSelfDelete(dir);
                    Invoke((Action)(() => Application.Exit()));
                    return;
                }
                Log("已取消删除，程序文件保留：" + dir);
            }

            Log("卸载完成。程序文件未删除：" + dir);
            Invoke((Action)Finish);
        }

        void Finish()
        {
            _prog.Visible = false;
            _btnGo.Text = "完成";
            _btnGo.Enabled = true;
            _btnCancel.Enabled = true;
            _done = true;
        }

        // Spawn a detached cleanup script that waits for THIS process to exit
        // (directory stays locked while the GUI exe is running), then removes
        // the program directory. Capped at 20 retries to never loop forever.
        void SpawnSelfDelete(string dir)
        {
            var script = "@echo off\r\n" +
                         "set /a n=0\r\n" +
                         ":retry\r\n" +
                         "rd /s /q \"" + dir + "\" >nul 2>&1\r\n" +
                         "if not exist \"" + dir + "\" goto done\r\n" +
                         "set /a n=n+1\r\n" +
                         "if %n% geq 20 goto done\r\n" +
                         "ping -n 2 127.0.0.1 >nul\r\n" +
                         "goto retry\r\n" +
                         ":done\r\n" +
                         "del \"%~f0\" >nul 2>&1\r\n";
            var tmp = Path.Combine(Path.GetTempPath(), "md_uninstall_cleanup.cmd");
            File.WriteAllText(tmp, script, Encoding.ASCII);
            Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + tmp + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true
            });
        }
    }

    static class Entry
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new UninstallForm());
        }
    }
}
