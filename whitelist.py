class WhitelistManager:
    """白名单管理器"""
    
    def __init__(self, whitelist: list[str] = None):
        """
        初始化白名单管理器
        
        Args:
            whitelist: 白名单列表，默认为空列表
        """
        self._whitelist = whitelist.copy() if whitelist else []
    
    def check_whitelist(self, user_sid: str) -> bool:
        """
        检查用户是否在白名单中
        
        Args:
            user_sid: 用户会话ID
            
        Returns:
            True 如果用户允许访问（白名单为空或用户在其中）
            False 如果用户不在白名单中
        """
        if not self._whitelist:
            return True
        return user_sid in self._whitelist
    
    def add_to_whitelist(self, user_sid: str) -> bool:
        """
        添加用户到白名单
        
        Args:
            user_sid: 要添加的用户会话ID
            
        Returns:
            True 如果添加成功
            False 如果用户已在白名单中
        """
        if user_sid in self._whitelist:
            return False
        self._whitelist.append(user_sid)
        return True
    
    def remove_from_whitelist(self, user_sid: str) -> bool:
        """
        从白名单移除用户
        
        Args:
            user_sid: 要移除的用户会话ID
            
        Returns:
            True 如果移除成功
            False 如果用户不在白名单中
        """
        if user_sid not in self._whitelist:
            return False
        self._whitelist.remove(user_sid)
        return True
    
    def get_whitelist(self) -> list[str]:
        """
        获取当前白名单
        
        Returns:
            白名单列表的副本
        """
        return self._whitelist.copy()
    
    def set_whitelist(self, whitelist: list[str]) -> None:
        """
        设置白名单

        Args:
            whitelist: 新的白名单列表
        """
        self._whitelist = whitelist.copy() if whitelist else []
