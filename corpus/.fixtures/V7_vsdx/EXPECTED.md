# V7 vsdx fixture 期望产物

- 源文件:`V7_合成流程图.vsdx`(最小 OOXML zip 空壳)
- 期望(LibreOffice 不可用环境):**永久 stub + `failed_no_libreoffice` 标记**(plan §7.3 步骤 4.3 降级路径)
- 期望(LibreOffice 可用环境):soffice headless 转 PDF → 走现有 G15/G16 路径 (本机未装,留 v0.2.1 hotfix 补)
