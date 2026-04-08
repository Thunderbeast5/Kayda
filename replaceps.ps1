$map = @{
    "#EFEBE9" = "surface-court"
    "#FAF9F6" = "surface-court"
    "#FBFBFA" = "surface-court"
    "#FCFBF8" = "surface-paperLight"
    "#FAF7F2" = "surface-paperMain"
    "#f0f0f0" = "surface-border"
    "#EBE7E0" = "surface-border"
    "#dcdcdc" = "surface-border"
    "#D7CCC8" = "surface-border"
    "#6D4C41" = "wood-light"
    "#4E342E" = "wood-light"
    "#3E2723" = "wood-dark"
    "#2E1A17" = "wood-deep"
    "#5D4037" = "primaryBrown"
    "#C5A059" = "gold"
    "#D32F2F" = "semantic-danger"
    "#B71C1C" = "semantic-dangerDark"
    "#8B0000" = "semantic-criticalText"
    "#E3F2FD" = "semantic-infoBg"
    "#90CAF9" = "semantic-infoBorder"
    "#0D47A1" = "semantic-infoText"
    "#1E88E5" = "semantic-infoAccent"
    "#212121" = "textPrimary"
    "#757575" = "textMuted"
    "#FFFFFF" = "surface-white"
    "#1565C0" = "semantic-infoText"
    "#bbdefb" = "semantic-infoBorder"
    "#64B5F6" = "semantic-infoAccent"
    "#e0e0e0" = "surface-border"
    "#FAEED1" = "surface-paperMain"
    "#FAFAFA" = "surface-court"
    "#BBDEFB" = "semantic-infoBorder"
    "#C62828" = "semantic-dangerDark"
    "#b08d4b" = "gold"
    "#8D6E63" = "textMuted"
    "#ccc" = "surface-border"
    "#FCEBA6" = "surface-paperMain"
}

Get-ChildItem -Path src -Recurse -Include *.jsx | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    foreach ($key in $map.Keys) {
        $val = $map[$key]
        $hex = $key.Substring(1)
        $re = "(bg|text|border|fill|ring|decoration|from|via|to)-\\[#$hex\\]"
        $content = [System.Text.RegularExpressions.Regex]::Replace($content, "(?i)$re", "`$1-$val")
    }
    Set-Content -Path $_.FullName -Value $content
}
