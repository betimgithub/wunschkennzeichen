--[[
    Remote Finder
    Durchsucht ReplicatedStorage (rekursiv) nach RemoteEvents und
    RemoteFunctions, deren Name eines der Suchwörter enthält, und
    gibt sie mit vollem Pfad im Output aus.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- Suchwörter (Groß-/Kleinschreibung egal). Bei Bedarf erweitern.
local KEYWORDS = {
    "egg", "hatch", "buy", "open",
    "chest", "creaking", "halloween", "treat", "candy", "knock",
}

-- true = ALLE Remotes ausgeben, ohne Filter (hilfreich, wenn die
-- Remotes kryptische Namen haben)
local SHOW_ALL = false

local function matchesKeyword(name)
    local lower = string.lower(name)
    for _, word in ipairs(KEYWORDS) do
        if string.find(lower, word, 1, true) then
            return true
        end
    end
    return false
end

local found = 0
print("========== Remote Finder: ReplicatedStorage ==========")

for _, obj in ipairs(ReplicatedStorage:GetDescendants()) do
    if obj:IsA("RemoteEvent") or obj:IsA("RemoteFunction") or obj:IsA("UnreliableRemoteEvent") then
        -- Auch den Pfad prüfen: oft heißt der Ordner "Eggs" und das Remote nur "Open"
        if SHOW_ALL or matchesKeyword(obj.Name) or matchesKeyword(obj:GetFullName()) then
            found += 1
            print(string.format("[%s] %s", obj.ClassName, obj:GetFullName()))
        end
    end
end

print(string.format("========== %d Treffer ==========", found))

-- ProximityPrompts (E-Taste) im Workspace – zeigt, wie das Ei geöffnet wird
print("========== ProximityPrompts im Workspace ==========")
local prompts = 0
for _, obj in ipairs(workspace:GetDescendants()) do
    if obj:IsA("ProximityPrompt") then
        local info = obj.ObjectText .. " " .. obj.ActionText
        if SHOW_ALL or matchesKeyword(info) or matchesKeyword(obj:GetFullName()) then
            prompts += 1
            print(string.format("[Prompt] %s | ObjectText=%q ActionText=%q",
                obj:GetFullName(), obj.ObjectText, obj.ActionText))
        end
    end
end
print(string.format("========== %d Prompts ==========", prompts))
