{-# LANGUAGE DeriveDataTypeable #-}

module Main where

import ResultsDB(getConnectionFromTrunk,addFilesToGroup,makeGroup,makeFailGroup,addFilesToFailGroup,getPostgresConnection)
import Database.HDBC(toSql,fromSql,withTransaction,prepare,execute,fetchRow,Statement)
import Database.HDBC.Types(IConnection)
import System.Console.CmdArgs
import Data.Maybe
import Control.Monad(void)

-- data UpdateType = CreateGroup | AppendToGroup
--                 deriving (Data,Typeable,Enum,Eq,Show)

data ManageTestGroup = CreateGroup
                       { groupDescription :: String
                       , files :: [String]
                       } |
                       AppendByDesc
                       { groupDescription :: String
                       , files :: [String]
                       } |
                       AppendById
                       { groupId :: Int
                       , files :: [String]
                       } |
                       AmendDesc
                       { groupId :: Int
                       , groupDescription :: String
                       } |
                       CreateFailGroup
                       { groupDescription :: String
                       , groupReason :: String
                       , fails :: [String]
                       } deriving (Data,Typeable,Show)

createDefaults :: ManageTestGroup
createDefaults = CreateGroup
             { groupDescription  = "" &= help "A description of this test group"
             , files = [] &= typ "FILES" &= args
             }

appendByDescDefaults :: ManageTestGroup
appendByDescDefaults = AppendByDesc
                       { groupDescription = "" &= help "The description of the group to update"
                       , files = [] &= typ "FILE" &= args
                       }
appendByIdDefaults :: ManageTestGroup
appendByIdDefaults = AppendById
                       { groupId = 0 &= help "The id of the group to update"
                       , files = [] &= typ "FILEs" &= args
                       }
amendDescDefaults :: ManageTestGroup
amendDescDefaults = AmendDesc
                    { groupId = 0 &= help "The id of the group to amend"
                    , groupDescription = "" &= help "The new description"
                    }

cfgflbDefaults :: ManageTestGroup
cfgflbDefaults = CreateFailGroup
                       { groupDescription = "" &= help "A description of this fail group"
                       , groupReason  = "" &= help "Why do these tests fail?"
                       , fails = [] &= typ "FAILS" &= args
                       }

stmtUpdateDesc :: String
stmtUpdateDesc = "UPDATE test_groups SET description=? WHERE id=?"

stmtGetGroupId :: String
stmtGetGroupId = "SELECT id FROM test_groups WHERE description=?"

updateDesc :: IConnection connection => Int -> String -> connection -> IO ()
updateDesc gid desc con = do
  stmt <- prepare con stmtUpdateDesc
  void $ execute stmt [toSql desc, toSql gid]

getGroupId :: IConnection connection => String -> connection -> IO Int
getGroupId desc con = do
  stmt <- prepare con stmtGetGroupId
  execute stmt [toSql desc]
  fmap (fromSql.head.fromJust) $ fetchRow stmt

dispatch :: IConnection connection => ManageTestGroup -> connection -> IO ()
dispatch (CreateGroup desc filenames) con = do
  gid <- makeGroup desc con
  addFilesToGroup gid filenames con
dispatch (AppendByDesc desc filenames) con = do
  gid <- getGroupId desc con
  addFilesToGroup gid filenames con
dispatch (AppendById gid filenames) con = addFilesToGroup gid filenames con
dispatch (AmendDesc gid desc) con = updateDesc gid desc con
dispatch (CreateFailGroup desc reason filenames) con = do
  gid <- makeFailGroup desc reason con
  addFilesToFailGroup gid filenames con

main :: IO ()
main = do
  opts <- cmdArgs (modes [createDefaults,appendByDescDefaults, appendByIdDefaults,amendDescDefaults,cfgflbDefaults])
  con <- getPostgresConnection
  withTransaction con $ dispatch opts
