// dist es salida generada. Editar exclusivamente src.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const source = path.join(__dirname, 'src');
const output = path.join(__dirname, 'dist');
function build() {
  const domain = JSON.parse(fs.readFileSync(path.join(source, 'domain.json'), 'utf8'));
  const constants =
    '// Generado desde domain.json.\n' +
    Object.entries(domain)
      .map(([name, values]) => 'const ' + name + '=Object.freeze(' + JSON.stringify(values) + ');')
      .join('\n') +
    '\n';
  if (fs.readFileSync(path.join(source, 'domain.js'), 'utf8') !== constants)
    fs.writeFileSync(path.join(source, 'domain.js'), constants);

  if (!fs.existsSync(path.join(source, 'index.html'))) throw new Error('Falta src/index.html');
  for (const file of fs.readdirSync(source).filter((f) => f.endsWith('.js'))) {
    execFileSync(process.execPath, ['--check', path.join(source, file)], { stdio: 'inherit' });
  }
  fs.mkdirSync(output, { recursive: true });
  function removeObsolete(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) removeObsolete(target);
      else if (!fs.existsSync(path.join(source, path.relative(output, target))))
        fs.unlinkSync(target);
    }
  }
  removeObsolete(output);
  fs.cpSync(source, output, {
    recursive: true,
    filter: (file) => !file.startsWith(path.join(source, 'backend')),
  });
  console.log('VitaDev: src → dist. Build correcto.');
}
build();
if (process.argv.includes('--watch')) {
  let timer;
  fs.watch(source, { recursive: true }, () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      try {
        build();
      } catch (error) {
        console.error(error.message);
      }
    }, 150);
  });
  console.log('Observando cambios en src…');
}
