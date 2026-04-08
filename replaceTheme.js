const fs = require('fs');
const path = require('path');

const walkSync = function(dir, filelist) {
  files = fs.readdirSync(dir);
  filelist = filelist || [];
  files.forEach(function(file) {
    if (fs.statSync(path.join(dir, file)).isDirectory()) {
      filelist = walkSync(path.join(dir, file), filelist);
    }
    else {
      if(file.endsWith('.jsx')) {
          filelist.push(path.join(dir, file));
      }
    }
  });
  return filelist;
};

const hexToClassMap = {
    // Backgrounds / Surfaces
    "#EFEBE9": "surface-court",
    "#FAF9F6": "surface-court",
    "#FBFBFA": "surface-court",
    "#FCFBF8": "surface-paperLight",
    "#FAF7F2": "surface-paperMain",
    "#f0f0f0": "surface-border",
    "#EBE7E0": "surface-border",
    "#dcdcdc": "surface-border",
    "#D7CCC8": "surface-border",

    // Wood / Furniture
    "#6D4C41": "wood-light",
    "#4E342E": "wood-light", // map similar shades
    "#3E2723": "wood-dark",
    "#2E1A17": "wood-deep",

    // Primary
    "#5D4037": "primaryBrown",
    "#C5A059": "gold",

    // Semantics
    "#D32F2F": "semantic-danger",
    "#B71C1C": "semantic-dangerDark",
    "#8B0000": "semantic-criticalText",
    "#E3F2FD": "semantic-infoBg",
    "#90CAF9": "semantic-infoBorder",
    "#0D47A1": "semantic-infoText",
    "#1E88E5": "semantic-infoAccent",
    
    // Text
    "#212121": "textPrimary",
    "#757575": "textMuted"
};

const dirsToScan = [path.join(__dirname, 'src')];
let allFiles = [];
dirsToScan.forEach(d => {
    allFiles = allFiles.concat(walkSync(d));
});

allFiles.forEach(file => {
    let content = fs.readFileSync(file, 'utf8');
    let original = content;
    
    // Replace hex references inside tailwind classes: e.g., bg-[#3E2723] -> bg-wood-dark
    Object.keys(hexToClassMap).forEach(hex => {
        // Regex to match anything like (bg|text|border|fill)-[#HEX]
        // Case insensitive hex
        const regexHex = hex.replace('#', '');
        const re = new RegExp(`(bg|text|border|fill)-\\[#${regexHex}\\]`, 'gi');
        content = content.replace(re, `$1-${hexToClassMap[hex]}`);
    });
    
    if (content !== original) {
        fs.writeFileSync(file, content, 'utf8');
        console.log("Updated: " + file);
    }
});
