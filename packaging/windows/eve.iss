; Instalador de LLMJarvis para Windows (Inno Setup 6).
;
;   iscc /DMiVersion=1.0.0 /DMiArch=x64 packaging\windows\eve.iss
;
; Registra el desinstalador en Agregar o quitar programas, y el asistente deja
; escrita la configuracion elegida antes del primer arranque.

#ifndef MiVersion
  #define MiVersion "1.0.0"
#endif
#ifndef MiArch
  #define MiArch "x64"
#endif

#define MiApp    "LLMJarvis"
#define MiNombre "Eve"
#define MiAutor  "EvanPalac1"
#define MiURL    "https://github.com/EvanPalac1/LLMJarvis"

[Setup]
AppId={{9F2C4E7A-5B31-4D8E-9A16-7C3D5E8F1B24}
AppName={#MiApp}
AppVersion={#MiVersion}
AppVerName={#MiApp} {#MiVersion}
AppPublisher={#MiAutor}
AppPublisherURL={#MiURL}
AppSupportURL={#MiURL}/issues
AppUpdatesURL={#MiURL}/releases
DefaultDirName={autopf}\{#MiApp}
DefaultGroupName={#MiApp}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=Eve-Setup-{#MiArch}
; build.py deja el icono aca antes de invocar a ISCC.
SetupIconFile=..\..\dist\eve.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Por usuario y sin UAC por defecto: la app vive en el perfil del usuario, su
; autostart es por usuario y sus datos van a %APPDATA%. Pedir admin para eso
; seria pedir de mas. `dialog` deja elegir instalar para todos si lo quieren.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MiApp} ({#MiNombre})
UninstallDisplayIcon={app}\Eve.exe
ArchitecturesAllowed=x64compatible arm64
ArchitecturesInstallIn64BitMode=x64compatible arm64

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; \
    GroupDescription: "Accesos:"
Name: "autostart"; Description: "Arrancar {#MiNombre} al iniciar Windows"; \
    GroupDescription: "Inicio:"

[Files]
Source: "..\..\dist\Eve\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MiNombre}"; Filename: "{app}\Eve.exe"
Name: "{group}\{#MiNombre} - configuracion"; Filename: "{app}\Eve-config.exe"
Name: "{group}\Desinstalar {#MiApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MiNombre}"; Filename: "{app}\Eve.exe"; Tasks: escritorio
Name: "{userstartup}\{#MiNombre}"; Filename: "{app}\Eve.exe"; Tasks: autostart

[Run]
Filename: "{app}\Eve.exe"; Description: "Iniciar {#MiNombre} ahora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  PaginaOpciones: TInputOptionWizardPage;
  PaginaMotor: TInputOptionWizardPage;
  PaginaTecla: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  PaginaMotor := CreateInputOptionPage(wpSelectTasks,
    'Motor de la IA',
    'Quien piensa por Eve.',
    'Se puede cambiar despues desde el panel de configuracion.',
    True, False);
  PaginaMotor.Add('Ollama local  -  gratis y sin conexion, nada sale de tu PC');
  PaginaMotor.Add('Suscripcion de Claude  -  necesita Claude Code instalado y logueado');
  PaginaMotor.Add('API key de Anthropic  -  se carga despues en el panel');
  PaginaMotor.SelectedValueIndex := 1;

  PaginaTecla := CreateInputQueryPage(PaginaMotor.ID,
    'Tecla para hablar',
    'Que tecla mantiene presionada para dictarle a Eve.',
    'El valor por defecto es f13 porque ningun otro programa la usa. Si tu keypad ' +
    'manda otra cosa, se averigua despues con "Eve.exe --check --tecla".');
  PaginaTecla.Add('Tecla:', False);
  PaginaTecla.Values[0] := 'f13';

  PaginaOpciones := CreateInputOptionPage(PaginaTecla.ID,
    'Descargas opcionales',
    'Eve puede bajar esto ahora o la primera vez que lo uses.',
    'Son archivos grandes. Si preferis, deja ambos sin marcar y se bajan solos cuando hagan falta.',
    False, False);
  PaginaOpciones.Add('Modelo de reconocimiento de voz (~460 MB)');
  PaginaOpciones.Add('Voz en español para que Eve hable (~63 MB)');
end;

function MotorElegido(): String;
begin
  case PaginaMotor.SelectedValueIndex of
    0: Result := 'ollama';
    1: Result := 'claude-code';
  else
    Result := 'api';
  end;
end;

procedure EscribirConfig();
var
  Carpeta, Archivo, Contenido, Docs, Tecla: String;
begin
  Carpeta := ExpandConstant('{userappdata}\{#MiApp}');
  ForceDirectories(Carpeta);
  Archivo := Carpeta + '\config.json';
  { No pisar la config de una instalacion anterior. }
  if FileExists(Archivo) then
    Exit;

  Docs := ExpandConstant('{userdocs}');
  StringChangeEx(Docs, '\', '\\', True);
  Tecla := Trim(PaginaTecla.Values[0]);
  if Tecla = '' then
    Tecla := 'f13';

  Contenido :=
    '{' + #13#10 +
    '  "engine": "' + MotorElegido() + '",' + #13#10 +
    '  "hotkey": "' + Tecla + '",' + #13#10 +
    '  "tts_provider": "sapi",' + #13#10 +
    '  "workdirs": ["' + Docs + '"]' + #13#10 +
    '}' + #13#10;
  SaveStringToFile(Archivo, Contenido, False);
end;

procedure DescargasOpcionales();
var
  Codigo: Integer;
begin
  if PaginaOpciones.Values[0] then
  begin
    WizardForm.StatusLabel.Caption := 'Descargando el modelo de voz (~460 MB)...';
    Exec(ExpandConstant('{app}\Eve.exe'), '--descargar-modelo', '',
         SW_HIDE, ewWaitUntilTerminated, Codigo);
  end;
  if PaginaOpciones.Values[1] then
  begin
    WizardForm.StatusLabel.Caption := 'Descargando la voz en español (~63 MB)...';
    Exec(ExpandConstant('{app}\Eve.exe'), '--descargar-voz', '',
         SW_HIDE, ewWaitUntilTerminated, Codigo);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    EscribirConfig();
    DescargasOpcionales();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Datos := ExpandConstant('{userappdata}\{#MiApp}');
    if DirExists(Datos) then
      { Decide el usuario: ahi viven su agenda, su memoria, el historial y las
        voces descargadas. Borrarlos en silencio seria una perdida sin aviso. }
      if MsgBox('Tambien queres borrar tus datos de Eve?' + #13#10#13#10 +
                'Incluye la agenda de contactos, la memoria, el historial de ' +
                'conversaciones y las voces descargadas.' + #13#10#13#10 +
                Datos,
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(Datos, True, True, True);
  end;
end;
