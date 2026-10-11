--[[
    Auto-Hatch
    Feuert ein RemoteEvent (oder ruft eine RemoteFunction auf) in einer
    eigenen Schleife per task.spawn, damit dein Hauptskript (Haus-Teleport)
    parallel weiterlaufen kann.

    Stoppen:  _G.AutoHatch = false
    Starten:  _G.AutoHatch = true  (Skript erneut ausführen)
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

------------------------------------------------------------------------
-- KONFIGURATION – hier deine Werte aus dem Remote Finder eintragen
------------------------------------------------------------------------
local CONFIG = {
    -- Pfad zum Remote ab ReplicatedStorage, jeder Ordner ein Eintrag.
    -- Beispiel: ReplicatedStorage.Remotes.Eggs.HatchEgg
    --        -> { "Remotes", "Eggs", "HatchEgg" }
    RemotePath = { "REMOTE_ORDNER", "REMOTE_NAME" },

    -- Argumente, die an den Server geschickt werden (Reihenfolge zählt!).
    -- Beispiele: { "Halloween Egg" }  oder  { "Halloween Egg", 1 }
    -- Leere Tabelle {} = keine Argumente.
    Arguments = { "EI_NAME" },

    -- Wartezeit zwischen zwei Versuchen in Sekunden.
    -- Nicht zu niedrig wählen – sonst Kick durch Server-Ratelimit.
    Interval = 1,

    -- Debug-Ausgabe für jeden Aufruf
    Verbose = false,
}
------------------------------------------------------------------------

-- Vorherige Instanz stoppen, falls das Skript mehrfach ausgeführt wird
_G.AutoHatch = false
task.wait(CONFIG.Interval + 0.1)
_G.AutoHatch = true

local function resolveRemote(path)
    local current = ReplicatedStorage
    for _, name in ipairs(path) do
        current = current:WaitForChild(name, 10)
        if not current then
            return nil, "nicht gefunden: " .. name
        end
    end
    return current
end

task.spawn(function()
    local remote, err = resolveRemote(CONFIG.RemotePath)
    if not remote then
        warn("[AutoHatch] Remote " .. err)
        return
    end

    local isFunction = remote:IsA("RemoteFunction")
    if not (isFunction or remote:IsA("RemoteEvent") or remote:IsA("UnreliableRemoteEvent")) then
        warn("[AutoHatch] " .. remote:GetFullName() .. " ist kein Remote (" .. remote.ClassName .. ")")
        return
    end

    print("[AutoHatch] gestartet: " .. remote:GetFullName())

    local count = 0
    while _G.AutoHatch do
        local ok, result = pcall(function()
            if isFunction then
                return remote:InvokeServer(table.unpack(CONFIG.Arguments))
            else
                remote:FireServer(table.unpack(CONFIG.Arguments))
            end
        end)

        count += 1
        if not ok then
            warn("[AutoHatch] Fehler: " .. tostring(result))
        elseif CONFIG.Verbose then
            print(string.format("[AutoHatch] #%d gesendet%s", count,
                isFunction and (" -> " .. tostring(result)) or ""))
        end

        task.wait(CONFIG.Interval)
    end

    print("[AutoHatch] gestoppt nach " .. count .. " Aufrufen")
end)

-- Ab hier läuft dein Hauptskript (z. B. Haus-Teleport) normal weiter.
