Add-Type -AssemblyName System.Drawing, System.Windows.Forms

# Load WinRT types
[Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null

function Get-TextFromScreenRegion($x, $y, $w, $h) {
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $g.Dispose()

    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    $bytes = $ms.ToArray()
    $ms.Dispose()

    $iras = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $writer = New-Object Windows.Storage.Streams.DataWriter $iras
    $writer.WriteBytes($bytes)
    $writer.StoreAsync().GetAwaiter().GetResult() | Out-Null
    $writer.DetachStream() | Out-Null

    $decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($iras).GetAwaiter().GetResult()
    $softwareBmp = $decoder.GetSoftwareBitmapAsync().GetAwaiter().GetResult()

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) {
        $lang = New-Object Windows.Globalization.Language('zh-Hans-CN')
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
    }

    $ocrResult = $engine.RecognizeAsync($softwareBmp).GetAwaiter().GetResult()
    return $ocrResult.Text
}

$res = Get-TextFromScreenRegion 0 0 400 200
Write-Host "OCR_RESULT: $res"
