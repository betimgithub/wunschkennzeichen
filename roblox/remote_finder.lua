--[[
    Remote Finder
    Durchsucht ReplicatedStorage (rekursiv) nach RemoteEvents und
    RemoteFunctions sowie den Workspace nach ProximityPrompts (E-Taste),
    deren Name eines der Suchwörter enthält, und gibt sie im Output aus.

    Jedes Objekt wird einzeln in pcall geprüft: gesperrte Objekte
    ("property is locked", "lacking capability" ...) werden übersprungen,
    statt das ganze Skript abzubrechen.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- Suchwörter (Groß-/Kleinschreibung egal). Bei Bedarf erweitern.
local KEYWORDS = {
    "egg", "hatch", "buy", "open",
    "chest", "creaking", "halloween", "treat", "candy", "knock",
}

-- true = ALLE Remotes/Prompts ausgeben, ohne Filter (hilfreich, wenn die
-- Remotes kryptische Namen haben)
local SHOW_ALL = false

local function matchesKeyword(text)
    local lower = string.lower(text)
    for _, word in ipairs(KEYWORDS) do
        if string.find(lower, word, 1, true) then
            return true
        end
    end
    return false
end

local function safeDescendants(root)
    local ok, list = pcall(function() return root:GetDescendants() end)
    if ok then return list end
    warn("[RemoteFinder] GetDescendants fehlgeschlagen für " .. tostring(root) .. ": " .. tostring(list))
    return {}
end

local skipped = 0

-- ReplicatedStorage: Remotes
local found = 0
print("========== Remotes in ReplicatedStorage ==========")
for _, obj in ipairs(safeDescendants(ReplicatedStorage)) do
    local ok, line = pcall(function()
        if obj:IsA("RemoteEvent") or obj:IsA("RemoteFunction") or obj:IsA("UnreliableRemoteEvent") then
            -- Auch den Pfad prüfen: oft heißt der Ordner "Eggs" und das Remote nur "Open"
            local path = obj:GetFullName()
            if SHOW_ALL or matchesKeyword(path) then
                return string.format("[%s] %s", obj.ClassName, path)
            end
        end
    end)
    if not ok then
        skipped += 1
    elseif line then
        found += 1
        print(line)
    end
end
print(string.format("========== %d Remotes ==========", found))

-- Workspace: ProximityPrompts (E-Taste) – zeigt, wie das Ei geöffnet wird
local prompts = 0
print("========== ProximityPrompts im Workspace ==========")
for _, obj in ipairs(safeDescendants(workspace)) do
    local ok, line = pcall(function()
        if obj:IsA("ProximityPrompt") then
            local path = obj:GetFullName()
            local objectText, actionText = "", ""
            pcall(function() objectText = obj.ObjectText end)
            pcall(function() actionText = obj.ActionText end)
            if SHOW_ALL or matchesKeyword(path .. " " .. objectText .. " " .. actionText) then
                return string.format("[Prompt] %s | ObjectText=%q ActionText=%q", path, objectText, actionText)
            end
        end
    end)
    if not ok then
        skipped += 1
    elseif line then
        prompts += 1
        print(line)
    end
end
print(string.format("========== %d Prompts ==========", prompts))

if skipped > 0 then
    print(string.format("(%d gesperrte Objekte übersprungen – normal, kein Problem)", skipped))
end
